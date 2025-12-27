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
from pathlib import Path
import math

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("sim_output")


import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'coord_transform'))
from utils.geo import local_to_wgs84, wgs84_to_local


class SimOutputNode:
    """仿真器输出节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.params = sdk.params

        # 获取参数
        host = self.params.get('simulator_host', 'localhost')
        port = self.params.get('simulator_port', 5555)
        timeout = self.params.get('timeout', 1000)

        # ZMQ 连接到仿真器
        logger.info(f"连接到仿真器: {host}:{port}")
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(f"tcp://{host}:{port}")
        self.socket.setsockopt(zmq.RCVTIMEO, timeout)
        self.socket.setsockopt(zmq.SNDTIMEO, timeout)

        # GPS 参考点：优先从仿真器获取，失败则使用参数默认值
        self.ref_lon, self.ref_lat = self._fetch_gps_ref()
        logger.info(f"GPS 参考点: ({self.ref_lon}, {self.ref_lat})")

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

        # 地块和车辆配置端口（新版本）
        self.ports['field'] = sdk.create_output_port('field_info')
        self.ports['vehicle'] = sdk.create_output_port('vehicle_config')
        logger.info("地块信息 输出端口已创建")
        logger.info("车辆配置 输出端口已创建")

        # 任务请求端口（兼容旧版本）
        self.ports['task'] = sdk.create_output_port('task_request')
        logger.info("任务请求 输出端口已创建（兼容旧版本）")

        # 任务ENU端口（新版本）
        self.ports['task_enu'] = sdk.create_output_port('task_enu')
        logger.info("任务ENU 输出端口已创建")

        # 读取当前地块与版本（带重试机制，避免启动竞态）
        self.field_data, self.field_version = self._get_field_with_retry(max_retries=5, retry_delay=0.5)
        logger.info(f"地块信息已读取: {self.field_data.get('type', 'unknown')} - "
                   f"{self.field_data.get('area', 0):.1f} m²")

        # 组装地块信息和车辆配置
        self.field_info = self._build_field_info()
        self.vehicle_config = self._build_vehicle_config()
        logger.info(f"地块信息已构建: {len(self.field_info['parcel']['outer'])} 个边界点, "
                   f"{len(self.field_info['parcel']['holes'])} 个孔洞")
        logger.info(f"车辆配置已构建: 幅宽={self.vehicle_config['implement_width_m']}m")

        # 组装任务ENU（新版本）
        self.task_enu = self._build_task_enu()
        logger.info(f"任务ENU已构建")

        # 组装任务请求（固定内容，兼容旧版本）
        self.task_request = self._build_task_request_legacy()
        logger.info(f"任务请求已构建（兼容旧版本）")

        # 频率控制
        output_frequency = self.params.get('output_frequency', 50.0)
        self.period = 1.0 / output_frequency
        logger.info(f"输出频率: {output_frequency} Hz (周期 {self.period*1000:.1f} ms)")

    def _fetch_gps_ref(self) -> tuple[float, float]:
        """
        从仿真器获取 GPS 参考点，失败则使用默认值

        Returns:
            (ref_lon, ref_lat) 元组
        """
        try:
            request = {"type": "get_config"}
            self.socket.send_json(request)
            response = self.socket.recv_json()
            if response.get("status") == "ok":
                config = response.get("config", {})
                gps_ref = config.get("gps_ref", {})
                lon = gps_ref.get("lon", 121.5)
                lat = gps_ref.get("lat", 31.2)
                logger.info(f"从仿真器获取 GPS 参考点: ({lon}, {lat})")
                return lon, lat
        except Exception as e:
            logger.warning(f"从仿真器获取 GPS 参考点失败: {e}")

        # 失败时使用默认值
        logger.warning("使用默认 GPS 参考点: (121.5, 31.2)")
        return 121.5, 31.2

    def _get_field_with_retry(self, max_retries: int = 5, retry_delay: float = 0.5) -> tuple[dict, int]:
        """
        带重试机制获取地块信息（解决启动竞态条件）

        参数：
        - max_retries: 最大重试次数
        - retry_delay: 重试间隔（秒）

        返回：
        - (地块数据, 版本号) 元组
        """
        for attempt in range(max_retries):
            field_data, version = self._get_field_current()

            # 如果成功获取真实地块（版本号 > 0），直接返回
            if version > 0:
                return field_data, version

            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                logger.warning(f"获取地块失败，重试 ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)

        # 所有重试失败，返回默认地块
        logger.warning(f"获取地块失败 {max_retries} 次，使用默认地块（将在主循环中继续尝试）")
        return self._default_field(), 0

    def _get_field_current(self) -> tuple[dict, int]:
        """从仿真器读取当前地块信息与版本"""
        try:
            request = {"type": "get_field"}
            self.socket.send_json(request)
            response = self.socket.recv_json()
            if response.get("status") == "ok":
                return response.get("field", {}), int(response.get("version", 1))
            else:
                logger.error(f"获取地块失败: {response.get('message', 'unknown error')}")
                return self._default_field(), 0
        except Exception as e:
            logger.error(f"获取地块异常: {e}")
            return self._default_field(), 0

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

    def _build_field_info(self) -> dict:
        """构建地块信息（新版本）"""
        # 将地块边界从笛卡尔坐标转换为GPS坐标
        boundary_meter = self.field_data.get("boundary", [])
        boundary_gps = [local_to_wgs84(x, y, self.ref_lon, self.ref_lat) for x, y in boundary_meter]

        # 同样转换孔洞（如果存在）
        holes_meter = self.field_data.get("holes", [])
        holes_gps = []
        if holes_meter:
            holes_gps = [[local_to_wgs84(x, y, self.ref_lon, self.ref_lat) for x, y in hole] for hole in holes_meter]
            logger.info(f"转换孔洞: {len(holes_gps)}个孔洞")

        # 同样转换出入口
        entry_points_meter = self.field_data.get("entry_points", [])
        entry_points_gps = [local_to_wgs84(x, y, self.ref_lon, self.ref_lat) for x, y in entry_points_meter]
        entries_formatted = [{'point': pt, 'type': 'entry'} for pt in entry_points_gps]

        logger.info(f"坐标转换: {len(boundary_meter)}个边界点 米→GPS")

        return {
            "field_name": self.field_data.get("type", "field"),
            "parcel": {
                "outer": boundary_gps,  # [(lon, lat), ...] WGS84格式
                "holes": holes_gps,     # [[(lon, lat), ...], ...] 多个孔洞
                "points": [],
                "entries": entries_formatted
            }
        }

    def _build_vehicle_config(self) -> dict:
        """构建车辆配置（新版本）"""
        return {
            "implement_width_m": self.params.get('implement_width_m', 3.0),
            "overlap_ratio": self.params.get('overlap_ratio', 0.1),
            "path_inset_m": self.params.get('path_inset_m', 1.0),
            "pivot_turn": self.params.get('pivot_turn', True),
            "yaw_rate_max_deg_s": self.params.get('yaw_rate_max_deg_s', 60.0),
            "min_turn_radius_m": self.params.get('min_turn_radius_m', 2.0)
        }

    def _build_task_request_legacy(self) -> dict:
        """构建任务请求（兼容旧版本）"""
        return {
            "id": f"task_{int(time.time())}",
            "parcel": self.field_info["parcel"],
            "vehicle": self.vehicle_config
        }

    def _build_task_enu(self) -> dict:
        """构建task_enu（使用地块第一个点作为参考点）"""
        boundary_meter = self.field_data.get("boundary", [])
        if not boundary_meter:
            logger.warning("地块边界为空，无法构建task_enu")
            return None

        # 1. 确定参考点：地块第一个点
        first_pt = boundary_meter[0]
        ref_lon, ref_lat = local_to_wgs84(
            first_pt[0], first_pt[1],
            self.ref_lon, self.ref_lat
        )

        # 2. 转换边界为ENU
        boundary_enu = []
        for x, y in boundary_meter:
            lon, lat = local_to_wgs84(x, y, self.ref_lon, self.ref_lat)
            ex, ey = wgs84_to_local(lon, lat, ref_lon, ref_lat)
            boundary_enu.append((ex, ey))

        # 3. 转换孔洞
        holes_enu = []
        for hole in self.field_data.get("holes", []):
            hole_enu = []
            for x, y in hole:
                lon, lat = local_to_wgs84(x, y, self.ref_lon, self.ref_lat)
                ex, ey = wgs84_to_local(lon, lat, ref_lon, ref_lat)
                hole_enu.append((ex, ey))
            holes_enu.append(hole_enu)

        logger.info(f"ENU转换: {len(boundary_enu)}个边界点, {len(holes_enu)}个孔洞, 参考点=({ref_lon:.6f}, {ref_lat:.6f})")

        return {
            'id': f"task_{int(time.time())}",
            'parcel': {
                'outer': boundary_enu,
                'holes': holes_enu,
            },
            'vehicle': self.vehicle_config,
            'ref_lon': ref_lon,
            'ref_lat': ref_lat,
            'timestamp': time.time()
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
        last_field_check = time.time()

        try:
            while True:
                start_time = time.time()

                # 检查地块版本刷新
                if time.time() - last_field_check >= 1.0:
                    try:
                        fld, ver = self._get_field_current()
                        if ver != self.field_version:
                            logger.info(f"检测到地块版本变化: {self.field_version} -> {ver}")
                            self.field_version = ver
                            self.field_data = fld
                            self.field_info = self._build_field_info()
                            self.task_enu = self._build_task_enu()
                            self.task_request = self._build_task_request_legacy()
                    except Exception as e:
                        logger.warning(f"地块刷新检查失败: {e}")
                    finally:
                        last_field_check = time.time()
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

                # 2. 持续发送地块和车辆配置（新版本）
                self.ports['field'].send(self.field_info)
                self.ports['vehicle'].send(self.vehicle_config)

                # 3. 持续发送任务ENU（新版本）
                if self.task_enu:
                    self.ports['task_enu'].send(self.task_enu)

                # 4. 持续发送任务请求（兼容旧版本）
                if loop_count == 0:
                    # 第一帧时输出详细日志
                    logger.debug(f"[SEND] field_info: {json.dumps(self.field_info, indent=2, ensure_ascii=False)}")
                    logger.debug(f"[SEND] vehicle_config: {json.dumps(self.vehicle_config, indent=2)}")
                self.ports['task'].send(self.task_request)

                # 4. 频率控制
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
