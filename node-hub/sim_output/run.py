#!/usr/bin/env python3
"""
仿真器输出节点
统一提供所有传感器数据和环境信息（地块+车辆配置）

包含坐标系转换：将仿真器的笛卡尔坐标（米）转换为GPS坐标（WGS84）
"""

import sys
import time
import zmq
import json
import logging
import math
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("sim_output")


class CoordinateConverter:
    """坐标系转换器（简化版）"""

    def __init__(self, ref_lon: float = 121.5, ref_lat: float = 31.2):
        self.ref_lon = ref_lon
        self.ref_lat = ref_lat
        self.meters_per_degree_lat = 111320.0
        lat_rad = math.radians(ref_lat)
        self.meters_per_degree_lon = 111320.0 * math.cos(lat_rad)

    def meter_to_gps(self, x: float, y: float):
        """笛卡尔坐标（米）→ GPS坐标（WGS84）"""
        lat = self.ref_lat + (y / self.meters_per_degree_lat)
        lon = self.ref_lon + (x / self.meters_per_degree_lon)
        return (lon, lat)


class SimOutputNode:
    """仿真器输出节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.params = sdk.params

        # 获取参数
        host = self.params.get('simulator_host', 'localhost')
        port = self.params.get('simulator_port', 5555)
        timeout = self.params.get('timeout', 1000)

        # 坐标转换器参数
        ref_lon = self.params.get('ref_longitude', 121.5)
        ref_lat = self.params.get('ref_latitude', 31.2)
        self.converter = CoordinateConverter(ref_lon=ref_lon, ref_lat=ref_lat)
        logger.info(f"坐标转换器已初始化: 参考点 ({ref_lon}, {ref_lat})")

        # ZMQ 连接到仿真器
        logger.info(f"连接到仿真器: {host}:{port}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(f"tcp://{host}:{port}")
        self.socket.setsockopt(zmq.RCVTIMEO, timeout)
        self.socket.setsockopt(zmq.SNDTIMEO, timeout)

        # 创建输出端口（根据配置）
        self.ports = {}
        self.enable_gps = self.params.get('enable_gps', True)
        self.enable_imu = self.params.get('enable_imu', True)
        self.enable_rtk = self.params.get('enable_rtk', True)
        self.enable_odometry = self.params.get('enable_odometry', False)
        self.enable_state = self.params.get('enable_state', False)

        if self.enable_gps:
            self.ports['gps'] = sdk.create_output_port('gps_fix')
            logger.info("GPS 输出端口已创建")

        if self.enable_imu:
            self.ports['imu'] = sdk.create_output_port('imu_data')
            logger.info("IMU 输出端口已创建")

        if self.enable_rtk:
            self.ports['rtk'] = sdk.create_output_port('rtk_fix')
            logger.info("RTK 输出端口已创建")

        if self.enable_odometry:
            self.ports['odom'] = sdk.create_output_port('odometry')
            logger.info("里程计 输出端口已创建")

        if self.enable_state:
            self.ports['state'] = sdk.create_output_port('state_info')
            logger.info("状态信息 输出端口已创建")

        # 任务请求端口（始终创建）
        self.ports['task'] = sdk.create_output_port('task_request')
        logger.info("任务请求 输出端口已创建")

        # 读取地块信息（只读一次）
        self.field_data = self._get_field_once()
        logger.info(f"地块信息已读取: {self.field_data.get('type', 'unknown')} - "
                   f"{self.field_data.get('area', 0):.1f} m²")

        # 组装任务请求（固定内容）
        self.task_request = self._build_task_request()
        logger.info(f"任务请求已构建: {len(self.task_request['parcel']['outer'])} 个边界点")

        # 频率控制
        output_frequency = self.params.get('output_frequency', 50.0)
        self.period = 1.0 / output_frequency
        logger.info(f"输出频率: {output_frequency} Hz (周期 {self.period*1000:.1f} ms)")

    def _get_field_once(self) -> dict:
        """从仿真器读取地块信息（只调用一次）"""
        try:
            request = {"type": "get_field"}
            self.socket.send_json(request)
            response = self.socket.recv_json()

            if response.get("status") == "ok":
                return response.get("field", {})
            else:
                logger.error(f"获取地块失败: {response.get('message', 'unknown error')}")
                return self._default_field()

        except zmq.error.Again:
            logger.error("获取地块超时，使用默认地块")
            return self._default_field()
        except Exception as e:
            logger.error(f"获取地块异常: {e}")
            return self._default_field()

    def _default_field(self) -> dict:
        """默认地块（100m x 200m 矩形）"""
        return {
            "type": "rectangular",
            "boundary": [(0, 0), (100, 0), (100, 200), (0, 200)],
            "width": 100.0,
            "length": 200.0,
            "area": 20000.0,
            "center": (50.0, 100.0),
            "obstacles": [],
            "entry_points": [(0.0, 0.0)]
        }

    def _build_task_request(self) -> dict:
        """组装规划任务请求"""
        # 将地块边界从笛卡尔坐标转换为GPS坐标
        boundary_meter = self.field_data.get("boundary", [])

        # 坐标转换：(x, y) 米 → (lon, lat) WGS84
        boundary_gps = [self.converter.meter_to_gps(x, y) for x, y in boundary_meter]

        # 同样转换出入口
        entry_points_meter = self.field_data.get("entry_points", [])
        entry_points_gps = [self.converter.meter_to_gps(x, y) for x, y in entry_points_meter]

        # 将出入口转换为正确的格式：List[Dict] with 'point' and 'type' keys
        entries_formatted = [{'point': pt, 'type': 'entry'} for pt in entry_points_gps]

        logger.info(f"坐标转换: {len(boundary_meter)}个边界点 米→GPS")
        logger.debug(f"  示例: {boundary_meter[0]} (米) → {boundary_gps[0]} (GPS)")

        return {
            "id": f"task_{int(time.time())}",
            "parcel": {
                "outer": boundary_gps,  # [(lon, lat), ...] WGS84格式
                "holes": [],
                "points": [],
                "entries": entries_formatted  # List[Dict] with 'point' and 'type' keys
            },
            "vehicle": {
                "implement_width_m": self.params.get('implement_width_m', 3.0),
                "overlap_ratio": self.params.get('overlap_ratio', 0.1),
                "path_inset_m": self.params.get('path_inset_m', 1.0),
                "pivot_turn": self.params.get('pivot_turn', True),
                "yaw_rate_max_deg_s": self.params.get('yaw_rate_max_deg_s', 60.0),
                "min_turn_radius_m": self.params.get('min_turn_radius_m', 2.0)
            }
        }

    def _get_sensor(self, sensor_name: str) -> dict:
        """从仿真器获取传感器数据"""
        try:
            request = {"type": "get_sensor", "sensor": sensor_name}
            self.socket.send_json(request)
            response = self.socket.recv_json()

            if response.get("status") == "ok":
                return response.get("data", {})
            else:
                logger.warning(f"获取{sensor_name}失败: {response.get('message', '')}")
                return {}

        except zmq.error.Again:
            logger.warning(f"获取{sensor_name}超时")
            return {}
        except Exception as e:
            logger.error(f"获取{sensor_name}异常: {e}")
            return {}

    def _get_state(self) -> dict:
        """从仿真器获取完整状态"""
        try:
            request = {"type": "get_state"}
            self.socket.send_json(request)
            response = self.socket.recv_json()

            if response.get("status") == "ok":
                return response.get("state", {})
            else:
                return {}

        except Exception as e:
            logger.error(f"获取状态异常: {e}")
            return {}

    def run(self):
        """主循环"""
        logger.info("仿真器输出节点已启动")

        loop_count = 0
        last_log_time = time.time()

        try:
            while True:
                start_time = time.time()

                # 1. 读取传感器数据
                if self.enable_gps:
                    gps_data = self._get_sensor("gps")
                    if gps_data:
                        self.ports['gps'].send(gps_data)

                if self.enable_imu:
                    imu_data = self._get_sensor("imu")
                    if imu_data:
                        self.ports['imu'].send(imu_data)

                if self.enable_rtk:
                    rtk_data = self._get_sensor("rtk_gps")
                    if rtk_data:
                        self.ports['rtk'].send(rtk_data)

                if self.enable_odometry:
                    odom_data = self._get_sensor("odometry")
                    if odom_data:
                        self.ports['odom'].send(odom_data)

                if self.enable_state:
                    state_data = self._get_state()
                    if state_data:
                        self.ports['state'].send(state_data)

                # 2. 持续发送任务请求（虽然内容固定）
                #    这样下游节点随时可以获取最新的任务
                if loop_count == 0:
                    # 第一帧时输出详细日志
                    logger.debug(f"[SEND] task_request type: {type(self.task_request)}")
                    logger.debug(f"[SEND] task_request: {json.dumps(self.task_request, indent=2, ensure_ascii=False)}")
                self.ports['task'].send(self.task_request)

                # 3. 频率控制
                loop_count += 1
                elapsed = time.time() - start_time
                sleep_time = max(0, self.period - elapsed)

                if sleep_time > 0:
                    time.sleep(sleep_time)

                # 定期日志
                if time.time() - last_log_time > 5.0:
                    logger.info(f"运行中 - 已输出 {loop_count} 帧")
                    last_log_time = time.time()

        except KeyboardInterrupt:
            logger.info("接收到停止信号")
        except Exception as e:
            logger.error(f"主循环异常: {e}", exc_info=True)
        finally:
            self.cleanup()

    def cleanup(self):
        """清理资源"""
        logger.info("清理资源...")
        self.socket.close()
        self.context.term()
        logger.info("仿真器输出节点已停止")


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="DEBUG") as sdk:
            node = SimOutputNode(sdk)
            node.run()
    except Exception as e:
        logger.error(f"节点启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
