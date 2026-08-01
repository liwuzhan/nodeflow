#!/usr/bin/env python3
"""
地块规划节点 - L3层主逻辑

节点模式：
- 作为 NodeFlow 节点运行
- 读取本地保存的地块配置文件
- 输出 task_enu 格式数据到 coord_transform

数据流：
    parcel_planner -> task_enu -> coord_transform
"""

import sys
import os
import time
import json
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from edge.sdk.nodeflow_sdk import NodeFlowSDK
from atom import gps_to_enu, convert_boundary_gps_to_enu, validate_boundary

# --- Schema Definitions ---

class TaskENU(BaseModel):
    id: str
    parcel: Dict[str, Any]
    vehicle: Dict[str, Any]
    ref_lon: float
    ref_lat: float
    timestamp: float
    plan_revision: int = 0

# --- End Schema Definitions ---


# 数据目录
DATA_DIR = Path(__file__).parent / 'data' / 'parcels'


def load_parcel_config(name: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    加载地块配置文件

    Args:
        name: 地块名称

    Returns:
        (地块配置字典, 错误信息)，成功时错误信息为 None
    """
    file_path = DATA_DIR / f'{name}.json'

    if not file_path.exists():
        return None, f"地块配置文件不存在: {file_path}"

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON 格式错误: {e}"
    except Exception as e:
        return None, f"读取文件失败: {e}"


def build_task_enu(parcel_config: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    从地块配置构建 task_enu 数据

    Args:
        parcel_config: 地块配置字典

    Returns:
        (task_enu 数据字典, 错误信息)，成功时错误信息为 None
    """
    try:
        name = parcel_config.get('name', 'unknown')
        ref_point = parcel_config.get('ref_point')
        boundary_enu = parcel_config.get('boundary_enu', [])
        holes_enu = parcel_config.get('holes_enu', [])
        vehicle = parcel_config.get('vehicle', {})

        if not ref_point:
            return None, f"地块 '{name}' 缺少 GPS 参考点"

        ref_lon = ref_point.get('lon')
        ref_lat = ref_point.get('lat')

        if ref_lon is None or ref_lat is None:
            return None, f"地块 '{name}' GPS 参考点不完整"

        # 如果没有预计算的 ENU 坐标，进行转换
        if not boundary_enu:
            boundary_gps = parcel_config.get('boundary_gps', [])
            if not boundary_gps:
                return None, f"地块 '{name}' 没有边界数据"

            boundary_enu = convert_boundary_gps_to_enu(boundary_gps, ref_lon, ref_lat)

        # 如果没有预计算的孔洞 ENU 坐标，进行转换
        if not holes_enu and parcel_config.get('holes_gps'):
            holes_gps = parcel_config.get('holes_gps', [])
            holes_enu = [convert_boundary_gps_to_enu(hole, ref_lon, ref_lat) for hole in holes_gps]

        # 验证边界
        is_valid, error_msg = validate_boundary(boundary_enu)
        if not is_valid:
            return None, f"地块 '{name}' 边界验证失败: {error_msg}"

        # 构建 parcel 数据结构（与 global_coverage 兼容）
        parcel_data = {
            'outer': boundary_enu,
            'holes': holes_enu,
            'points': []
        }

        vehicle_config = {
            'implement_width_m': vehicle.get('implement_width_m', 2.0),
            'overlap_ratio': vehicle.get('overlap_ratio', 0.1),
            'path_inset_m': vehicle.get('path_inset_m', 0.5)
        }

        task_enu = {
            'id': f'parcel_{name}',
            'parcel': parcel_data,
            'vehicle': vehicle_config,
            'ref_lon': ref_lon,
            'ref_lat': ref_lat,
            'timestamp': time.time(),
            'plan_revision': int(
                parcel_config.get('plan_revision', parcel_config.get('field_revision', 0)) or 0
            ),
        }

        return task_enu, None

    except Exception as e:
        return None, f"构建任务数据异常: {e}"


class ParcelPlannerNode:
    """地块规划节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 读取参数
        self.parcel_name = sdk.params.get('parcel_name', 'default')
        self.web_port = int(sdk.params.get('web_port', 8081))
        self.send_interval = float(sdk.params.get('send_interval', 1.0))

        # 创建输出端口
        self.output_task_enu = sdk.create_output_port('task_enu', schema=TaskENU)

        # 发送状态
        self._last_sent_data = None   # 上次发送的数据（用于变更检测）
        self._last_file_mtime = 0.0   # 上次文件修改时间
        self._error_count = 0         # 连续错误计数
        self._max_error_log = 3       # 连续错误最多打印几次

        sdk.logger.info("=" * 60)
        sdk.logger.info("地块规划节点启动")
        sdk.logger.info(f"  地块名称: {self.parcel_name}")
        sdk.logger.info(f"  数据目录: {DATA_DIR}")
        sdk.logger.info(f"  发送间隔: {self.send_interval}s")
        sdk.logger.info("=" * 60)

    def _get_file_mtime(self) -> float:
        """获取当前地块文件的修改时间"""
        file_path = DATA_DIR / f'{self.parcel_name}.json'
        try:
            return file_path.stat().st_mtime if file_path.exists() else 0.0
        except OSError:
            return 0.0

    def _data_changed(self, task_enu: Dict[str, Any]) -> bool:
        """
        检测数据是否发生变化（排除 timestamp 字段）

        Args:
            task_enu: 当前构建的 task_enu 数据

        Returns:
            True 如果数据有变化或首次发送
        """
        if self._last_sent_data is None:
            return True

        # 比较除 timestamp 外的所有字段
        for key in task_enu:
            if key == 'timestamp':
                continue
            if task_enu.get(key) != self._last_sent_data.get(key):
                return True

        return False

    def load_and_send(self) -> bool:
        """
        加载地块配置并发送（仅在数据变化时发送）

        Returns:
            True 如果成功，False 否则
        """
        # 检查文件修改时间，未变化则跳过（不重复发送相同数据）
        current_mtime = self._get_file_mtime()
        if self._last_sent_data is not None and current_mtime == self._last_file_mtime:
            # 文件未变化，跳过发送（避免触发下游节点的无意义工作）
            return True

        # 加载配置
        parcel_config, load_error = load_parcel_config(self.parcel_name)

        if load_error:
            self._error_count += 1
            if self._error_count <= self._max_error_log:
                self.sdk.logger.error(f"加载地块失败: {load_error}")
                if self._error_count == 1:
                    self.sdk.logger.info(f"  请先运行工具创建地块: python3 {Path(__file__).parent / 'test_tool.py'}")
            elif self._error_count == self._max_error_log + 1:
                self.sdk.logger.warning("后续相同错误将不再重复打印")
            return False

        # 构建 task_enu
        task_enu, build_error = build_task_enu(parcel_config)

        if build_error:
            self._error_count += 1
            if self._error_count <= self._max_error_log:
                self.sdk.logger.error(f"构建任务数据失败: {build_error}")
            elif self._error_count == self._max_error_log + 1:
                self.sdk.logger.warning("后续相同错误将不再重复打印")
            return False

        # 错误恢复
        if self._error_count > 0:
            self.sdk.logger.info(f"错误已恢复（之前连续失败 {self._error_count} 次）")
            self._error_count = 0

        # 检测数据变化
        changed = self._data_changed(task_enu)

        # 只有在数据真正变化时才发送（避免触发下游节点的无意义工作）
        if not changed:
            # 更新文件修改时间缓存，避免重复加载
            self._last_file_mtime = current_mtime
            return True

        # 数据有变化，发送并打印日志
        ref_lon = task_enu['ref_lon']
        ref_lat = task_enu['ref_lat']
        boundary_points = len(task_enu['parcel']['outer'])
        holes_count = len(task_enu['parcel'].get('holes', []))

        if self._last_sent_data is None:
            self.sdk.logger.info(f"首次发送地块: {self.parcel_name}")
        else:
            self.sdk.logger.info(f"地块数据已更新: {self.parcel_name}")

        self.sdk.logger.info(f"  GPS参考点: ({ref_lon:.6f}, {ref_lat:.6f})")
        self.sdk.logger.info(f"  边界点数: {boundary_points}, 孔洞: {holes_count}")
        self.sdk.logger.info(f"  车辆: 幅宽={task_enu['vehicle']['implement_width_m']}m, "
                             f"重叠={task_enu['vehicle']['overlap_ratio']}")

        # 发送数据并缓存
        self.output_task_enu.send(task_enu)
        self._last_sent_data = task_enu
        self._last_file_mtime = current_mtime

        return True

    def run(self):
        """主循环"""
        self.sdk.logger.info(f"开始发送 task_enu（间隔 {self.send_interval}s）...")

        while True:
            self.load_and_send()

            # 检查参数更新（支持运行时切换地块）
            new_parcel_name = self.sdk.params.get('parcel_name')
            if new_parcel_name and new_parcel_name != self.parcel_name:
                self.sdk.logger.info(f"切换地块: {self.parcel_name} -> {new_parcel_name}")
                self.parcel_name = new_parcel_name
                self._last_sent_data = None
                self._last_file_mtime = 0.0
                self._error_count = 0

            time.sleep(self.send_interval)


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            node = ParcelPlannerNode(sdk)
            node.run()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
