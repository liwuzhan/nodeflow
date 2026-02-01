#!/usr/bin/env python3
"""
Logger 节点 - L3层主逻辑

功能：
- 类似磁带，可记录和回放任意数据流
- 10个输入/输出通道，any类型
- 支持记录、回放两种模式
"""

import sys
import time
import os
from pathlib import Path

# 添加项目根目录以访问SDK
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加当前节点目录
sys.path.insert(0, str(Path(__file__).parent))

from sdk.nodeflow_sdk import NodeFlowSDK
import atom

# 数据目录
DATA_DIR = Path(__file__).parent / 'data' / 'recordings'

# 通道数量
NUM_CHANNELS = 10


class LoggerNode:
    """Logger 节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 读取参数
        self.mode = sdk.params.get('mode', 'record')
        self.record_name = sdk.params.get('record_name', 'recording')
        self.playback_speed = float(sdk.params.get('playback_speed', 1.0))
        self.loop_playback = sdk.params.get('loop_playback', False)
        self.max_records = int(sdk.params.get('max_records', 10))

        # 创建输入输出端口
        self.input_ports = []
        self.output_ports = []

        for i in range(NUM_CHANNELS):
            self.input_ports.append(sdk.create_input_port(f'input_{i}'))
            self.output_ports.append(sdk.create_output_port(f'output_{i}'))

        # 状态变量
        self.current_frame_data = {}  # 当前帧数据（各通道最新值）
        self.recorded_frames = []     # 记录的帧数据
        self.playback_frames = []     # 回放的帧数据
        self.playback_index = 0       # 当前回放索引
        self.last_playback_time = 0   # 上次回放时间
        self.playback_interval = 0.05 # 回放间隔

        # 确保数据目录存在
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.sdk.logger.info("=" * 60)
        self.sdk.logger.info("Logger 节点启动")
        self.sdk.logger.info(f"  运行模式: {self.mode}")
        self.sdk.logger.info(f"  通道数量: {NUM_CHANNELS}")
        self.sdk.logger.info(f"  数据目录: {DATA_DIR}")
        if self.mode == 'playback':
            self.sdk.logger.info(f"  回放速度: {self.playback_speed}x")
            self.sdk.logger.info(f"  循环回放: {self.loop_playback}")
        self.sdk.logger.info("=" * 60)

        # 初始化模式
        if self.mode == 'playback':
            self._load_for_playback()

    def _load_for_playback(self):
        """加载最新的记录用于回放"""
        records = atom.list_records(str(DATA_DIR))
        if not records:
            raise RuntimeError("没有找到可回放的记录文件")

        # 加载最新的记录
        latest_record = records[0]
        filepath = latest_record['path']
        self.playback_frames = atom.load_record(filepath)

        if self.playback_frames:
            self.sdk.logger.info(f"已加载记录: {latest_record['name']}")
            self.sdk.logger.info(f"  帧数: {len(self.playback_frames)}")
            self.sdk.logger.info(f"  时长: {latest_record['duration']:.2f}s")
            self.playback_interval = atom.calculate_playback_interval(
                self.playback_frames, self.playback_speed
            )
            self.sdk.logger.info(f"  回放间隔: {self.playback_interval*1000:.1f}ms")
        else:
            raise RuntimeError(f"加载记录失败: {filepath}")

    def _read_all_inputs(self) -> dict:
        """读取所有输入端口的最新值"""
        frame_data = {}
        for i, port in enumerate(self.input_ports):
            data = port.recv_latest()
            if data is not None:
                frame_data[f'channel_{i}'] = data
        return frame_data

    def _write_all_outputs(self, frame_data: dict):
        """写入所有输出端口（仅回放模式使用）"""
        for i, port in enumerate(self.output_ports):
            channel_key = f'channel_{i}'
            if channel_key in frame_data:
                port.send(frame_data[channel_key])

    def _cleanup_old_records(self):
        """清理旧的记录文件"""
        old_files = atom.get_old_records(str(DATA_DIR), self.max_records)
        for filepath in old_files:
            try:
                os.remove(filepath)
                self.sdk.logger.info(f"已删除旧记录: {Path(filepath).name}")
            except Exception as e:
                self.sdk.logger.warning(f"删除文件失败: {filepath}, {e}")

    def run(self):
        """主循环"""
        while True:
            current_time = time.time()

            if self.mode == 'record':
                self._run_record_mode(current_time)
            elif self.mode == 'playback':
                self._run_playback_mode(current_time)

            time.sleep(0.01)  # 100Hz

    def _run_record_mode(self, current_time: float):
        """记录模式：接收输入并保存"""
        # 读取所有输入
        frame_data = self._read_all_inputs()

        # 有数据则记录
        if frame_data:
            # 创建帧
            frame = atom.create_frame(current_time, frame_data)
            self.recorded_frames.append(frame)

        # 定期保存到文件（每100帧打印一次）
        if len(self.recorded_frames) % 100 == 0:
            self.sdk.logger.debug(f"已记录 {len(self.recorded_frames)} 帧")

    def _run_playback_mode(self, current_time: float):
        """回放模式：从记录读取并发送到输出"""
        if not self.playback_frames:
            return

        # 检查是否该发送下一帧
        if current_time - self.last_playback_time >= self.playback_interval:
            frame = atom.get_frame_at_index(self.playback_frames, self.playback_index)

            if frame:
                # 提取各通道数据并输出
                for i in range(NUM_CHANNELS):
                    channel_key = f'channel_{i}'
                    data = atom.extract_channel_data(frame, channel_key)
                    if data is not None:
                        self.output_ports[i].send(data)

                self.playback_index += 1
                self.last_playback_time = current_time

                # 检查是否回放结束
                if self.playback_index >= len(self.playback_frames):
                    if self.loop_playback:
                        self.playback_index = 0
                        self.sdk.logger.info("回放结束，重新开始")
                    else:
                        self.sdk.logger.info("回放结束，停止输出")
                        # 保持最后状态，不再发送新数据
                        return

    def cleanup(self):
        """清理资源"""
        if self.mode == 'record' and self.recorded_frames:
            # 保存记录
            filepath = atom.generate_record_path(str(DATA_DIR), self.record_name)
            if atom.save_record(filepath, self.recorded_frames):
                self.sdk.logger.info(f"记录已保存: {filepath}")
                self.sdk.logger.info(f"  帧数: {len(self.recorded_frames)}")

                # 清理旧记录
                self._cleanup_old_records()
            else:
                self.sdk.logger.error("保存记录失败")


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            node = LoggerNode(sdk)

            try:
                node.run()
            except KeyboardInterrupt:
                node.sdk.logger.info("收到关闭信号")
            finally:
                node.cleanup()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
