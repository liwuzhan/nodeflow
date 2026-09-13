#!/usr/bin/env python3
"""
RTK驱动节点主程序
高精度GPS定位数据采集与输出
"""

import sys
import time
import math

from edge.sdk.nodeflow_sdk import NodeFlowSDK, die
if __package__:
    from .nmea_parser import NMEAParser
    from .device_interface import create_interface
else:
    from nmea_parser import NMEAParser
    from device_interface import create_interface


class RTKDriverNode:
    """RTK驱动节点"""

    def __init__(self):
        """初始化RTK驱动节点"""
        # 初始化SDK
        self.sdk = NodeFlowSDK(log_level="INFO")
        self.logger = self.sdk.logger

        self.logger.info("RTK Driver Node initializing...")

        # 获取参数
        self.serial_port = self.sdk.get_param("serial_port", "/dev/ttyUSB0")
        self.serial_baudrate = self.sdk.get_param("serial_baudrate", 115200)
        self.serial_timeout = self.sdk.get_param("serial_timeout", 1.0)
        self.use_network = self.sdk.get_param("use_network", False)
        self.network_host = self.sdk.get_param("network_host", "192.168.1.100")
        self.network_port = self.sdk.get_param("network_port", 5000)
        self.network_protocol = self.sdk.get_param("network_protocol", "tcp")
        self.nmea_message = self.sdk.get_param("nmea_message", "KSXT")
        self.output_frequency = self.sdk.get_param("output_frequency", 20)
        self.min_rtk_quality = self.sdk.get_param("min_rtk_quality", 3)
        self.min_satellites = self.sdk.get_param("min_satellites", 10)
        self.enable_smoothing = self.sdk.get_param("enable_smoothing", False)
        self.smoothing_alpha = self.sdk.get_param("smoothing_alpha", 0.3)
        self.heading_source = self.sdk.get_param("heading_source", "dual_antenna")
        # 兼容旧真机图的 device 名称；两者均要求设备双天线实测航向。
        if self.heading_source == "device":
            self.heading_source = "dual_antenna"
        if self.heading_source != "dual_antenna":
            raise ValueError("rtk_driver requires heading_source=dual_antenna; "
                             "course over ground is not antenna heading")
        self.heading_timeout_s = float(self.sdk.get_param("heading_timeout_s", 0.5))
        self.enable_raw_log = self.sdk.get_param("enable_raw_log", False)
        self.raw_log_path = self.sdk.get_param("raw_log_path", "/tmp/rtk_raw.log")

        # 天线安装校准参数
        self.antenna_offset_x = self.sdk.get_param("antenna_offset_x", 0.0)
        self.antenna_offset_y = self.sdk.get_param("antenna_offset_y", 0.0)
        self.heading_offset_deg = self.sdk.get_param("heading_offset_deg", 0.0)

        # 创建输出端口
        self.output_port = self.sdk.create_output_port("rtk_fix")

        # 创建设备接口
        config = {
            "use_network": self.use_network,
            "serial_port": self.serial_port,
            "serial_baudrate": self.serial_baudrate,
            "serial_timeout": self.serial_timeout,
            "network_host": self.network_host,
            "network_port": self.network_port,
            "network_protocol": self.network_protocol
        }
        self.device = create_interface(config)

        # 创建NMEA解析器
        self.parser = NMEAParser(heading_timeout_s=self.heading_timeout_s)

        # 状态变量
        self.last_valid_data = None
        self.smoothed_lat = None
        self.smoothed_lon = None
        self.smoothed_alt = None
        self.message_count = 0
        self.error_count = 0
        self.last_output_time = 0.0
        self.output_interval = 1.0 / self.output_frequency

        # 原始数据日志
        self.raw_log_file = None
        if self.enable_raw_log:
            try:
                self.raw_log_file = open(self.raw_log_path, 'w')
                self.logger.info(f"Raw NMEA logging enabled: {self.raw_log_path}")
            except Exception as e:
                self.logger.error(f"Failed to open raw log file: {e}")

        self.logger.info(f"RTK Driver configured:")
        self.logger.info(f"  Connection: {'Network' if self.use_network else 'Serial'}")
        if self.use_network:
            self.logger.info(f"  Network: {self.network_protocol.upper()}://{self.network_host}:{self.network_port}")
        else:
            self.logger.info(f"  Serial: {self.serial_port} @ {self.serial_baudrate} bps")
        self.logger.info(f"  NMEA Message: {self.nmea_message}")
        self.logger.info(f"  Output Frequency: {self.output_frequency} Hz")
        self.logger.info(f"  Min RTK Quality: {self.min_rtk_quality}")
        self.logger.info(f"  Min Satellites: {self.min_satellites}")

    def setup(self):
        """连接RTK设备并配置"""
        self.logger.info("Connecting to RTK device...")

        # 尝试连接（最多重试5次）
        max_retries = 5
        for attempt in range(max_retries):
            if self.device.connect():
                self.logger.info("✓ RTK device connected")
                break
            else:
                self.logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed")
                if attempt < max_retries - 1:
                    time.sleep(2.0)
        else:
            raise RuntimeError("Failed to connect to RTK device after multiple attempts")

        # 配置RTK设备输出频率
        time.sleep(1.0)  # 等待设备稳定
        self._configure_device()

        self.logger.info("RTK Driver Node ready")

    def loop(self):
        """主循环：读取并解析NMEA数据"""
        # 检查连接状态，如果断开则尝试重连
        if not self.device.is_connected():
            self.parser.reset_heading()
            self.logger.warning("Device disconnected, attempting to reconnect...")
            if self.device.connect():
                self.logger.info("✓ Device reconnected")
            else:
                # 连接失败，跳过本次循环
                time.sleep(1.0)
                return

        # 读取一行NMEA数据
        line = self.device.read_line(timeout=0.1)

        if not line:
            return

        # 记录原始数据
        if self.raw_log_file:
            try:
                self.raw_log_file.write(line + '\n')
                self.raw_log_file.flush()
            except:
                pass

        # 解析NMEA消息
        data = self.parser.parse(line)

        if not data:
            return

        self.message_count += 1

        # 检查数据完整性和质量
        if not self._validate_data(data):
            return

        # 应用平滑滤波（如果启用）
        if self.enable_smoothing and 'lat' in data and 'lon' in data:
            data = self._apply_smoothing(data)

        # 应用天线安装偏移补偿
        data = self._apply_antenna_calibration(data)

        # 构造输出数据包
        output = self._build_output_packet(data)

        # 控制输出频率
        current_time = time.time()
        if current_time - self.last_output_time >= self.output_interval:
            self.output_port.send(output)
            self.last_output_time = current_time
            self.last_valid_data = data

            # 每10秒输出一次状态
            if self.message_count % (self.output_frequency * 10) == 0:
                self._log_status(data)

    def cleanup(self):
        """清理资源"""
        self.logger.info("Shutting down RTK Driver Node...")

        # 关闭设备连接
        if self.device:
            self.device.disconnect()

        # 关闭原始日志文件
        if self.raw_log_file:
            try:
                self.raw_log_file.close()
            except:
                pass

        # 关闭SDK
        self.sdk.shutdown()

        self.logger.info(f"Total messages processed: {self.message_count}")
        self.logger.info(f"Total errors: {self.error_count}")
        self.logger.info("RTK Driver Node stopped")

    def _configure_device(self):
        """配置RTK设备输出"""
        self.logger.info("Configuring RTK device output...")

        # 构造配置命令（UM982命令格式：<消息名> <周期秒>，如 GPRMC 0.05 = 20Hz）
        commands = []

        # 注意: 不能发送 UNLOG/UNLOGALL，会停掉 GGA/RMC 触发看门狗重启
        # 只添加或修改输出频率

        # 配置主要NMEA消息输出
        period = 1.0 / self.output_frequency  # 转换为周期（秒）
        commands.append(f"{self.nmea_message} {period}")

        # 如果使用GPGGA+GPRMC组合，需要配置两个消息
        if self.nmea_message in ("GPGGA", "GNGGA"):
            commands.append(f"GPRMC {period}")
        elif self.nmea_message in ("GPRMC", "GNRMC"):
            commands.append(f"GPGGA {period}")

        # 双天线航向：额外配置 GPTHS 输出
        if self.heading_source == "dual_antenna":
            commands.append(f"GPTHS {period}")

        # 发送配置命令
        for cmd in commands:
            if self.device.write(cmd):
                self.logger.debug(f"Sent command: {cmd}")
                time.sleep(0.1)
            else:
                self.logger.warning(f"Failed to send command: {cmd}")

        self.logger.info("Device configuration complete")

    def _validate_data(self, data: dict) -> bool:
        """
        验证RTK数据质量

        Args:
            data: 解析后的数据字典

        Returns:
            True如果数据有效
        """
        # 检查必要字段
        if 'lat' not in data or 'lon' not in data:
            return False

        # 检查RTK质量
        rtk_quality = data.get('rtk_quality', 0)
        if rtk_quality < self.min_rtk_quality:
            if rtk_quality == 0:
                self.logger.debug("Waiting for RTK fix...")
            elif rtk_quality == 1:
                self.logger.debug("GPS single point mode (waiting for RTK fix)")
            elif rtk_quality == 2:
                self.logger.debug("RTK float solution (waiting for fixed)")
            return False

        # 检查卫星数量（RMC不含卫星数，跳过）
        num_sats = data.get('num_satellites', 0)
        if num_sats > 0 and num_sats < self.min_satellites:
            self.logger.debug(f"Insufficient satellites: {num_sats}/{self.min_satellites}")
            return False

        # 检查坐标合理性
        lat = data['lat']
        lon = data['lon']
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            self.logger.warning(f"Invalid coordinates: lat={lat}, lon={lon}")
            self.error_count += 1
            return False

        return True

    def _apply_smoothing(self, data: dict) -> dict:
        """
        应用指数平滑滤波

        Args:
            data: 原始数据

        Returns:
            平滑后的数据
        """
        alpha = self.smoothing_alpha

        if self.smoothed_lat is None:
            # 初始化
            self.smoothed_lat = data['lat']
            self.smoothed_lon = data['lon']
            self.smoothed_alt = data.get('alt', 0.0)
        else:
            # 指数平滑
            self.smoothed_lat = alpha * data['lat'] + (1 - alpha) * self.smoothed_lat
            self.smoothed_lon = alpha * data['lon'] + (1 - alpha) * self.smoothed_lon
            self.smoothed_alt = alpha * data.get('alt', 0.0) + (1 - alpha) * self.smoothed_alt

        # 更新数据
        data['lat'] = self.smoothed_lat
        data['lon'] = self.smoothed_lon
        data['alt'] = self.smoothed_alt

        return data

    def _apply_antenna_calibration(self, data: dict) -> dict:
        """
        应用天线安装偏移补偿

        将天线位置/航向校正到车体中心：
        1. heading 校正：减去航向安装偏移（度）
        2. 位置校正：根据校正后的 heading，将天线坐标平移到车体中心

        注意：heading 为地理坐标系（北=0°, CW正, [0,360)）

        Args:
            data: 包含 lat/lon/heading 的数据字典

        Returns:
            校正后的数据
        """
        METERS_PER_DEG_LAT = 111320.0

        # 原始主天线→从天线的角度单独保留；安装角只应用一次。
        heading = data.get('heading')
        if data.get('heading_valid') is False or heading is None:
            return data
        heading = float(heading)
        if not math.isfinite(heading):
            data['heading'] = None
            data['heading_valid'] = False
            return data
        data['antenna_heading_deg'] = heading % 360.0
        data['heading_offset_deg'] = self.heading_offset_deg
        data['heading'] = (heading - self.heading_offset_deg) % 360.0

        # 位置校正
        if (self.antenna_offset_x != 0.0 or self.antenna_offset_y != 0.0) \
                and 'lat' in data and 'lon' in data and 'heading' in data:
            # 地理度数转数学弧度用于三角运算
            heading_rad = math.radians(90.0 - data['heading'])
            lat_rad = math.radians(data['lat'])

            # 车体坐标系(前x右y) → ENU坐标系(东x北y) 的旋转
            dx_enu = self.antenna_offset_x * math.cos(heading_rad) \
                + self.antenna_offset_y * math.sin(heading_rad)
            dy_enu = self.antenna_offset_x * math.sin(heading_rad) \
                - self.antenna_offset_y * math.cos(heading_rad)

            # 天线偏移取反：天线在前方 → 车体中心在天线后方
            data['lon'] = data['lon'] - dx_enu / (METERS_PER_DEG_LAT * math.cos(lat_rad))
            data['lat'] = data['lat'] - dy_enu / METERS_PER_DEG_LAT

        return data

    def _build_output_packet(self, data: dict) -> dict:
        """
        构造输出数据包（sensor.rtk格式）

        Args:
            data: 解析后的数据

        Returns:
            输出数据包
        """
        # 基础定位数据
        output = {
            'timestamp': data.get('timestamp', time.time()),
            'lat': data['lat'],
            'lon': data['lon'],
            'alt': data.get('alt', 0.0),
            'heading': data.get('heading'),
            'heading_valid': data.get('heading_valid', False),
            'heading_mode': data.get('heading_mode', 'dual_antenna'),
            'rtk_status': self._get_rtk_status_string(data.get('rtk_quality', 0)),
            'rtk_quality': data.get('rtk_quality', 0),
            'num_satellites': data.get('num_satellites', 0),
        }
        for key in ('heading_source', 'heading_age_s', 'antenna_heading_deg',
                    'heading_offset_deg', 'ground_track_deg', 'timestamp_source'):
            if key in data:
                output[key] = data[key]

        # 可选字段（如果存在）
        if 'ground_speed' in data:
            output['ground_speed'] = data['ground_speed']

        if 'vel_east' in data and 'vel_north' in data:
            output['vel_east'] = data['vel_east']
            output['vel_north'] = data['vel_north']
            output['vel_up'] = data.get('vel_up', 0.0)

        if 'pitch' in data:
            output['pitch'] = data['pitch']

        if 'roll' in data:
            output['roll'] = data['roll']

        if 'hdop' in data:
            output['hdop'] = data['hdop']

        if 'heading_quality' in data:
            output['heading_quality'] = data['heading_quality']

        if 'num_satellites_heading' in data:
            output['num_satellites_heading'] = data['num_satellites_heading']

        return output

    def _get_rtk_status_string(self, quality: int) -> str:
        """获取RTK状态字符串"""
        status_map = {
            0: "INVALID",
            1: "SINGLE",
            2: "FLOAT",
            3: "FIXED"
        }
        return status_map.get(quality, "UNKNOWN")

    def _log_status(self, data: dict):
        """记录RTK状态"""
        rtk_status = self._get_rtk_status_string(data.get('rtk_quality', 0))
        num_sats = data.get('num_satellites', 0)
        heading = data.get('heading')
        heading_text = f"{heading:.1f}°" if heading is not None else "invalid"

        self.logger.info(
            f"RTK Status: {rtk_status} | "
            f"Sats: {num_sats} | "
            f"Pos: ({data['lat']:.8f}, {data['lon']:.8f}) | "
            f"Heading: {heading_text} | "
            f"Messages: {self.message_count}"
        )


def main():
    """主函数"""
    node = None
    try:
        node = RTKDriverNode()
        node.setup()

        # 主循环
        while True:
            node.loop()
            time.sleep(0.001)  # 1ms循环周期

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        if node:
            node.logger.error(f"Fatal error: {e}", exc_info=True)
        die(f"Fatal error: {e}")
    finally:
        if node:
            node.cleanup()


if __name__ == "__main__":
    main()
