#!/usr/bin/env python3
"""
RTK驱动节点主程序
高精度GPS定位数据采集与输出
"""

import sys
import time
import math
from pathlib import Path

# 添加SDK路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK
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
        self.min_rtk_quality = self.sdk.get_param("min_rtk_quality", 4)
        self.min_satellites = self.sdk.get_param("min_satellites", 10)
        self.enable_smoothing = self.sdk.get_param("enable_smoothing", False)
        self.smoothing_alpha = self.sdk.get_param("smoothing_alpha", 0.3)
        self.heading_source = self.sdk.get_param("heading_source", "dual_antenna")
        self.enable_raw_log = self.sdk.get_param("enable_raw_log", False)
        self.raw_log_path = self.sdk.get_param("raw_log_path", "/tmp/rtk_raw.log")

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
        self.parser = NMEAParser()

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

        # 构造配置命令
        commands = []

        # 停止所有输出
        commands.append(f"UNLOG {self.nmea_message}")

        # 配置主要NMEA消息输出
        commands.append(f"{self.nmea_message} {self.output_frequency}")

        # 如果使用GPGGA+GPRMC组合，需要配置两个消息
        if self.nmea_message == "GPGGA":
            commands.append(f"GPRMC {self.output_frequency}")
        elif self.nmea_message == "GPRMC":
            commands.append(f"GPGGA {self.output_frequency}")

        # 发送配置命令
        for cmd in commands:
            if self.device.write(cmd):
                self.logger.debug(f"Sent command: {cmd}")
                time.sleep(0.1)
            else:
                self.logger.warning(f"Failed to send command: {cmd}")

        # 保存配置（可选）
        # self.device.write("SAVECONFIG")

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

        # 检查卫星数量
        num_sats = data.get('num_satellites', 0)
        if num_sats < self.min_satellites:
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
            'heading': data.get('heading', 0.0),
            'rtk_status': self._get_rtk_status_string(data.get('rtk_quality', 0)),
            'rtk_quality': data.get('rtk_quality', 0),
            'num_satellites': data.get('num_satellites', 0),
        }

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
        heading_deg = math.degrees(data.get('heading', 0.0))

        self.logger.info(
            f"RTK Status: {rtk_status} | "
            f"Sats: {num_sats} | "
            f"Pos: ({data['lat']:.8f}, {data['lon']:.8f}) | "
            f"Heading: {heading_deg:.1f}° | "
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
        else:
            print(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        if node:
            node.cleanup()


if __name__ == "__main__":
    main()
