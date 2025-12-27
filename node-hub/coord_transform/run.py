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
from sdk.utils.geo import wgs84_to_local, heading_geo_to_math


class CoordTransformNode:
    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 获取GPS参考点 (优先级: 参数 > 环境变量 > 默认值)
        self.ref_lon = self._get_ref_coordinate('ref_longitude', 'GPS_REF_LON', 121.5)
        self.ref_lat = self._get_ref_coordinate('ref_latitude', 'GPS_REF_LAT', 31.2)

        sdk.logger.info(f"GPS参考点: ({self.ref_lon:.6f}, {self.ref_lat:.6f})")

        # 创建端口
        self.input_port = sdk.create_input_port('rtk_fix')
        self.output_port = sdk.create_output_port('pose_enu')

        # 统计
        self.transform_count = 0

    def _get_ref_coordinate(self, param_name: str, env_name: str, default: float) -> float:
        """
        获取GPS参考坐标

        优先级:
        1. 节点参数 (node.yaml 或 workflow配置)
        2. 环境变量
        3. 默认值
        """
        # 1. 从参数读取
        param_val = self.sdk.params.get(param_name)
        if param_val is not None:
            self.sdk.logger.info(f"{param_name} 从参数读取: {param_val}")
            return float(param_val)

        # 2. 从环境变量读取
        env_val = os.getenv(env_name)
        if env_val:
            self.sdk.logger.info(f"{param_name} 从环境变量{env_name}读取: {env_val}")
            return float(env_val)

        # 3. 使用默认值
        self.sdk.logger.warning(f"{param_name}未配置,使用默认值: {default}")
        return default

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
        self.sdk.logger.info("坐标转换节点启动")

        while True:
            rtk_data = self.input_port.recv_latest()

            if rtk_data:
                pose_enu = self.transform(rtk_data)
                if pose_enu:
                    self.output_port.send(pose_enu)

            time.sleep(0.01)  # 100Hz


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        node = CoordTransformNode(sdk)
        node.run()


if __name__ == "__main__":
    main()
