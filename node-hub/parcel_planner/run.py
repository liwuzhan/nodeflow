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

# 添加项目根目录以访问SDK
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加当前节点目录
sys.path.insert(0, str(Path(__file__).parent))

from sdk.nodeflow_sdk import NodeFlowSDK
from atom import gps_to_enu, convert_boundary_gps_to_enu, validate_boundary

# --- Schema Definitions ---

class TaskENU(BaseModel):
    id: str
    parcel: Dict[str, Any]
    vehicle: Dict[str, Any]
    ref_lon: float
    ref_lat: float
    timestamp: float

# --- End Schema Definitions ---


# 数据目录
DATA_DIR = Path(__file__).parent / 'data' / 'parcels'


def load_parcel_config(name: str) -> Optional[Dict[str, Any]]:
    """
    加载地块配置文件

    Args:
        name: 地块名称

    Returns:
        地块配置字典，失败返回 None
    """
    file_path = DATA_DIR / f'{name}.json'

    if not file_path.exists():
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return None


def build_task_enu(parcel_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    从地块配置构建 task_enu 数据

    Args:
        parcel_config: 地块配置字典

    Returns:
        task_enu 数据字典，失败返回 None
    """
    try:
        name = parcel_config.get('name', 'unknown')
        ref_point = parcel_config.get('ref_point')
        boundary_enu = parcel_config.get('boundary_enu', [])
        holes_enu = parcel_config.get('holes_enu', [])
        vehicle = parcel_config.get('vehicle', {})

        # 验证数据
        if not ref_point:
            print(f"错误: 地块 {name} 缺少 GPS 参考点")
            return None

        ref_lon = ref_point.get('lon')
        ref_lat = ref_point.get('lat')

        if ref_lon is None or ref_lat is None:
            print(f"错误: 地块 {name} GPS 参考点不完整")
            return None

        # 如果没有预计算的 ENU 坐标，进行转换
        if not boundary_enu:
            boundary_gps = parcel_config.get('boundary_gps', [])
            if not boundary_gps:
                print(f"错误: 地块 {name} 没有边界数据")
                return None

            boundary_enu = convert_boundary_gps_to_enu(boundary_gps, ref_lon, ref_lat)

        # 如果没有预计算的孔洞 ENU 坐标，进行转换
        if not holes_enu and parcel_config.get('holes_gps'):
            holes_gps = parcel_config.get('holes_gps', [])
            holes_enu = [convert_boundary_gps_to_enu(hole, ref_lon, ref_lat) for hole in holes_gps]

        # 验证边界
        is_valid, error_msg = validate_boundary(boundary_enu)
        if not is_valid:
            print(f"错误: 地块 {name} 边界验证失败: {error_msg}")
            return None

        # 构建 parcel 数据结构（与 global_coverage 兼容）
        parcel_data = {
            'outer': boundary_enu,
            'holes': holes_enu,  # 支持孔洞
            'points': []  # 当前版本不支持点障碍
        }

        # 车辆配置
        vehicle_config = {
            'implement_width_m': vehicle.get('implement_width_m', 2.0),
            'overlap_ratio': vehicle.get('overlap_ratio', 0.1),
            'path_inset_m': vehicle.get('path_inset_m', 0.5)
        }

        # 构建 task_enu
        task_enu = {
            'id': f'parcel_{name}',
            'parcel': parcel_data,
            'vehicle': vehicle_config,
            'ref_lon': ref_lon,
            'ref_lat': ref_lat,
            'timestamp': time.time()
        }

        return task_enu

    except Exception as e:
        print(f"错误: 构建任务数据失败: {e}")
        traceback.print_exc()
        return None


class ParcelPlannerNode:
    """地块规划节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 读取参数
        self.parcel_name = sdk.params.get('parcel_name', 'default')
        self.web_port = int(sdk.params.get('web_port', 8081))

        # 创建输出端口
        self.output_task_enu = sdk.create_output_port('task_enu', schema=TaskENU)

        # 统计
        self.send_count = 0

        sdk.logger.info("=" * 60)
        sdk.logger.info("地块规划节点启动")
        sdk.logger.info(f"地块名称: {self.parcel_name}")
        sdk.logger.info(f"数据目录: {DATA_DIR}")
        sdk.logger.info("=" * 60)

    def load_and_send(self) -> bool:
        """
        加载地块配置并发送

        Returns:
            True 如果成功，False 否则
        """
        # 加载配置
        parcel_config = load_parcel_config(self.parcel_name)

        if not parcel_config:
            self.sdk.logger.error(f"✗ 无法加载地块配置: {self.parcel_name}")
            self.sdk.logger.info(f"   请先运行独立工具创建地块配置:")
            self.sdk.logger.info(f"   python3 {Path(__file__).parent / 'test_tool.py'}")
            return False

        # 构建 task_enu
        task_enu = build_task_enu(parcel_config)

        if not task_enu:
            self.sdk.logger.error(f"✗ 构建任务数据失败")
            return False

        # 发送数据
        self.output_task_enu.send(task_enu)
        self.send_count += 1

        if self.send_count == 1:
            ref_lon = task_enu['ref_lon']
            ref_lat = task_enu['ref_lat']
            boundary_points = len(task_enu['parcel']['outer'])
            holes_count = len(task_enu['parcel'].get('holes', []))

            self.sdk.logger.info("-" * 60)
            self.sdk.logger.info(f"✓ 地块配置加载成功: {self.parcel_name}")
            self.sdk.logger.info(f"  GPS参考点: ({ref_lon:.6f}°, {ref_lat:.6f}°)")
            self.sdk.logger.info(f"  边界点数: {boundary_points}")
            if holes_count > 0:
                self.sdk.logger.info(f"  孔洞数量: {holes_count}")
            self.sdk.logger.info(f"  作业幅宽: {task_enu['vehicle']['implement_width_m']}m")
            self.sdk.logger.info(f"  重叠率: {task_enu['vehicle']['overlap_ratio']}")
            self.sdk.logger.info("-" * 60)
        elif self.send_count % 100 == 0:
            self.sdk.logger.debug(f"[发送计数] 已发送{self.send_count}次")

        return True

    def run(self):
        """主循环"""
        self.sdk.logger.info("开始持续发送 task_enu 数据...")

        while True:
            # 持续发送地块配置
            self.load_and_send()

            # 检查参数更新（支持运行时切换地块）
            new_parcel_name = self.sdk.params.get('parcel_name')
            if new_parcel_name and new_parcel_name != self.parcel_name:
                self.sdk.logger.info(f"切换地块: {self.parcel_name} -> {new_parcel_name}")
                self.parcel_name = new_parcel_name
                self.send_count = 0

            time.sleep(0.1)  # 10Hz 发送频率


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
