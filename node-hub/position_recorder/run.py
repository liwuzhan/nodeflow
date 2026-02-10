#!/usr/bin/env python3
"""
位置记录节点 - L3层主逻辑

功能：
- 接收RTK定位数据
- 提供Web界面进行手动/自动记录
- 保存记录到文件
- 自动清理旧记录（保留最近N次）
"""

import sys
import os
import time
import json
import threading
from pathlib import Path

# 添加项目根目录以访问SDK
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加当前节点目录
sys.path.insert(0, str(Path(__file__).parent))

from sdk.nodeflow_sdk import NodeFlowSDK
import atom
from web_server import app, socketio, set_record_callback

# 数据目录
DATA_DIR = Path(__file__).parent / 'data' / 'records'


class PositionRecorderNode:
    """位置记录节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 读取参数
        self.web_port = int(sdk.params.get('web_port', 8082))
        self.auto_record_interval = float(sdk.params.get('auto_record_interval', 1.0))
        self.max_records = int(sdk.params.get('max_records', 10))
        self.record_format = sdk.params.get('record_format', 'csv')

        # 创建数据目录
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # 创建输入端口
        self.input_rtk = sdk.create_input_port('rtk_fix')

        # 状态变量
        self.current_rtk_data = None
        self.recording_points = []
        self.is_recording = False
        self.auto_record_enabled = False
        self.record_start_time = None
        self.last_auto_record_time = 0
        self.record_count = 0

        # 设置Web服务器的回调
        set_record_callback(self)

        sdk.logger.info("=" * 60)
        sdk.logger.info("位置记录节点启动")
        sdk.logger.info(f"  数据目录: {DATA_DIR}")
        sdk.logger.info(f"  Web端口: {self.web_port}")
        sdk.logger.info(f"  自动记录间隔: {self.auto_record_interval}s")
        sdk.logger.info(f"  最大保留记录: {self.max_records}")
        sdk.logger.info(f"  记录格式: {self.record_format}")
        sdk.logger.info("=" * 60)

    def _cleanup_old_records(self):
        """清理旧的记录文件"""
        old_files = atom.get_old_records(str(DATA_DIR), self.max_records)
        for filepath in old_files:
            try:
                os.remove(filepath)
                self.sdk.logger.info(f"已删除旧记录: {Path(filepath).name}")
            except Exception as e:
                self.sdk.logger.warning(f"删除文件失败: {filepath}, {e}")

    def get_current_status(self) -> dict:
        """获取当前状态（供Web服务器调用）"""
        return {
            'is_recording': self.is_recording,
            'point_count': len(self.recording_points),
            'current_rtk': self.current_rtk_data,
            'record_start_time': self.record_start_time,
            'elapsed_seconds': time.time() - self.record_start_time if self.record_start_time else 0
        }

    def start_recording(self) -> dict:
        """开始记录"""
        if self.is_recording:
            return {'success': False, 'error': '已在记录中'}

        self.recording_points = []
        self.is_recording = True
        self.record_start_time = time.time()
        self.last_auto_record_time = 0

        self.sdk.logger.info("开始记录位置点")
        return {'success': True, 'message': '开始记录'}

    def stop_recording(self) -> dict:
        """停止记录"""
        if not self.is_recording:
            return {'success': False, 'error': '当前没有在记录'}

        self.is_recording = False

        # 保存记录
        result = self._save_record()

        self.sdk.logger.info(f"停止记录，已保存 {len(self.recording_points)} 个点")
        return result

    def add_point(self) -> dict:
        """手动添加当前点"""
        if not self.is_recording:
            return {'success': False, 'error': '请先点击"开始记录"'}

        if not atom.validate_rtk_data(self.current_rtk_data):
            return {'success': False, 'error': '当前RTK数据无效'}

        index = len(self.recording_points) + 1
        point = atom.format_record_point(self.current_rtk_data, index, 'manual')
        self.recording_points.append(point)

        self.sdk.logger.debug(f"手动记录点 #{index}: ({point['lat']:.8f}, {point['lon']:.8f})")
        return {'success': True, 'point': point, 'count': len(self.recording_points)}

    def toggle_auto_record(self, enabled: bool) -> dict:
        """切换自动记录模式"""
        self.auto_record_enabled = enabled
        self.sdk.logger.info(f"自动记录: {'启用' if enabled else '禁用'}")
        return {'success': True, 'auto_record_enabled': enabled}

    def clear_points(self) -> dict:
        """清除当前记录的点"""
        count = len(self.recording_points)
        self.recording_points = []
        self.sdk.logger.info(f"已清除 {count} 个记录点")
        return {'success': True, 'cleared_count': count}

    def _save_record(self) -> dict:
        """保存记录到文件"""
        if not self.recording_points:
            return {'success': False, 'error': '没有记录点'}

        # 生成文件名
        self.record_count += 1
        filename = atom.generate_filename(f"record_{self.record_count:04d}", self.record_format)
        filepath = DATA_DIR / filename

        # 保存文件
        if self.record_format == 'json':
            metadata = {
                'name': f'Record {self.record_count:04d}',
                'created_at': time.time(),
                'auto_record_interval': self.auto_record_interval
            }
            success = atom.save_record_json(str(filepath), self.recording_points, metadata)
        else:
            success = atom.save_record_csv(str(filepath), self.recording_points)

        if success:
            self.sdk.logger.info(f"记录已保存: {filename}")

            # 清理旧记录
            self._cleanup_old_records()

            return {
                'success': True,
                'filename': filename,
                'point_count': len(self.recording_points),
                'summary': atom.format_record_summary(self.recording_points)
            }
        else:
            return {'success': False, 'error': '保存文件失败'}

    def get_records_list(self) -> list:
        """获取已保存的记录列表"""
        records = []
        if not DATA_DIR.exists():
            return records

        for file_path in DATA_DIR.glob('record_*.*'):
            try:
                stat = file_path.stat()
                records.append({
                    'name': file_path.name,
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'modified_iso': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
                })
            except Exception:
                pass

        # 按修改时间倒序排列
        records.sort(key=lambda x: x['modified'], reverse=True)
        return records

    def run(self):
        """主循环"""
        # 启动Web服务器（在单独线程中）
        web_thread = threading.Thread(
            target=self._run_web_server,
            daemon=True
        )
        web_thread.start()

        self.sdk.logger.info("开始处理RTK数据...")

        while True:
            # 接收RTK数据
            rtk_data = self.input_rtk.recv_latest()
            if rtk_data:
                self.current_rtk_data = rtk_data

                # 自动记录模式
                if self.is_recording and self.auto_record_enabled:
                    current_time = time.time()
                    if current_time - self.last_auto_record_time >= self.auto_record_interval:
                        index = len(self.recording_points) + 1
                        point = atom.format_record_point(rtk_data, index, 'auto')
                        self.recording_points.append(point)
                        self.last_auto_record_time = current_time

                        self.sdk.logger.debug(
                            f"自动记录点 #{index}: ({point['lat']:.8f}, {point['lon']:.8f})"
                        )

            time.sleep(0.05)  # 20Hz

    def _run_web_server(self):
        """运行Web服务器"""
        self.sdk.logger.info(f"Web服务器启动: http://0.0.0.0:{self.web_port}")
        socketio.run(app, host='0.0.0.0', port=self.web_port, debug=False, allow_unsafe_werkzeug=True)


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            node = PositionRecorderNode(sdk)
            node.run()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
