#!/usr/bin/env python3
"""
坐标系转换节点 - WGS84 → ENU

将RTK GPS数据从WGS84坐标系转换为ENU局部笛卡尔坐标系，
简化下游节点的计算（使用欧几里得距离和atan2）。
"""
import sys
import os
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from .utils.geo import wgs84_to_local, heading_geo_to_math


class CoordTransformNode:
    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 网关模式: 等待task_enu来获取参考点
        self.ref_lon = None
        self.ref_lat = None
        self.task_received = False

        # 创建端口
        self.input_task_enu = sdk.create_input_port('task_enu')
        self.input_rtk = sdk.create_input_port('rtk_fix')

        self.output_task_enu = sdk.create_output_port('task_enu')
        self.output_pose_enu = sdk.create_output_port('pose_enu')

        # 统计
        self.transform_count = 0

        sdk.logger.info("坐标转换节点（网关模式）- 等待task_enu")

    def wait_for_task(self) -> bool:
        """
        等待接收task_enu并提取GPS参考点

        返回:
            True 如果成功接收到有效的task_enu
            False 否则
        """
        if self.task_received:
            return True

        task_data = self.input_task_enu.recv_latest()
        if task_data:
            self.ref_lon = task_data.get('ref_lon')
            self.ref_lat = task_data.get('ref_lat')

            if self.ref_lon is not None and self.ref_lat is not None:
                self.task_received = True
                self.sdk.logger.info(
                    f"✓ 接收task_enu，参考点: ({self.ref_lon:.6f}, {self.ref_lat:.6f})"
                )
                # 立即转发task_enu到下游
                self.output_task_enu.send(task_data)
                return True

        return False

    def transform(self, rtk_data: dict) -> dict:
        """
        将WGS84坐标转换为ENU坐标

        输入: rtk_fix (WGS84)
            - latitude: 纬度 (度)
            - longitude: 经度 (度)
            - heading: 航向角 (度, 北=0, CW正)

        输出: pose_enu
            - x: 东向距离 (米)
            - y: 北向距离 (米)
            - theta: 航向角 (弧度, 东=0, CCW正)
        """
        if not rtk_data:
            return None

        lat = rtk_data.get('latitude')
        lon = rtk_data.get('longitude')
        heading_deg = rtk_data.get('heading', 0.0)

        if lat is None or lon is None:
            return None

        # 1. 位置转换: WGS84 → ENU (米)
        x, y = wgs84_to_local(lon, lat, self.ref_lon, self.ref_lat)

        # 2. 航向角转换: 地理坐标系(度, 北=0, CW正) → 数学坐标系(弧度, 东=0, CCW正)
        theta = heading_geo_to_math(heading_deg)

        # 3. 构建输出
        pose_enu = {
            'x': x,
            'y': y,
            'theta': theta,
            'timestamp': rtk_data.get('timestamp', time.time()),
            'rtk_status': rtk_data.get('rtk_status', 'unknown')
        }

        self.transform_count += 1
        if self.transform_count % 100 == 0:
            self.sdk.logger.debug(f"已转换{self.transform_count}个RTK数据点 | 当前ENU: ({x:.2f}, {y:.2f}, θ={theta:.3f}rad)")

        return pose_enu

    def run(self):
        self.sdk.logger.info("坐标转换节点启动（网关模式）")

        while True:
            # 1. 等待task_enu
            if not self.wait_for_task():
                time.sleep(0.1)
                continue

            # 2. 处理RTK数据（只有在task接收到之后）
            rtk_data = self.input_rtk.recv_latest()
            if rtk_data:
                pose_enu = self.transform(rtk_data)
                if pose_enu:
                    self.output_pose_enu.send(pose_enu)

            # 3. 持续转发task_enu
            task_data = self.input_task_enu.recv_latest()
            if task_data:
                self.output_task_enu.send(task_data)

            time.sleep(0.01)  # 100Hz


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        node = CoordTransformNode(sdk)
        node.run()


if __name__ == "__main__":
    main()
