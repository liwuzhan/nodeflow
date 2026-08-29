#!/usr/bin/env python3
"""
RTK GPS定位节点
模拟RTK定位接收器，定期输出GPS定位数据
"""

import sys
import time
import random
import serial
from pathlib import Path

# 添加SDK路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.nodeflow_sdk import NodeFlowSDK, die


def simulate_gps_data(sequence):
    """
    生成模拟GPS数据

    参数：
    - sequence: 数据序列号

    返回：
    - GPS定位数据字典
    """
    # 以北京附近为基准，模拟随机漂移
    base_lat = 39.9042
    base_lon = 116.4074

    return {
        'seq': sequence,
        'timestamp': time.time(),
        'latitude': base_lat + random.uniform(-0.01, 0.01),
        'longitude': base_lon + random.uniform(-0.01, 0.01),
        'altitude': 50.0 + random.uniform(-5, 5),
        'fix_type': 'RTK',
        'num_satellites': random.randint(15, 30),
        'horizontal_accuracy': random.uniform(0.01, 0.05),
        'vertical_accuracy': random.uniform(0.02, 0.1),
        'velocity_east': random.uniform(-2, 2),
        'velocity_north': random.uniform(-2, 2),
        'velocity_up': random.uniform(-0.5, 0.5),
    }


def main():
    """主函数"""
    try:
        # 初始化SDK
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("RTK GPS Node started")

            # 获取参数
            device = sdk.require_param('device')
            baudrate = sdk.get_param('baudrate', 115200)
            update_rate_hz = sdk.get_param('update_rate_hz', 10.0)
            simulation_mode = sdk.get_param('simulation_mode', True)

            sdk.logger.info(f"Configuration:")
            sdk.logger.info(f"  Device: {device}")
            sdk.logger.info(f"  Baudrate: {baudrate}")
            sdk.logger.info(f"  Update Rate: {update_rate_hz} Hz")
            sdk.logger.info(f"  Simulation Mode: {simulation_mode}")

            # 创建输出端口
            output_port = sdk.create_output_port('gps_fix')

            # 主循环
            sequence = 0
            interval = 1.0 / update_rate_hz
            
            serial_conn = None
            if not simulation_mode:
                try:
                    serial_conn = serial.Serial(
                        port=device,
                        baudrate=baudrate,
                        timeout=0.1
                    )
                    sdk.logger.info(f"Connected to {device} at {baudrate}")
                except Exception as e:
                    sdk.logger.error(f"Failed to connect to serial port: {e}")
                    # 如果连接失败，是否要退出或者回退到模拟模式？
                    # 这里选择继续尝试连接或报错
                    # 为了演示稳健性，我们可以进入一个重试循环，或者抛出异常
                    pass # let the loop handle it

            sdk.logger.info("Starting main loop...")

            try:
                while True:
                    # 生成或读取GPS数据
                    if simulation_mode:
                        gps_data = simulate_gps_data(sequence)
                        output_port.send(gps_data)
                        sequence += 1
                        time.sleep(interval)
                    else:
                        # 实际读取串口数据
                        if serial_conn and serial_conn.is_open:
                            try:
                                if serial_conn.in_waiting > 0:
                                    line = serial_conn.readline().decode('ascii', errors='ignore').strip()
                                    if line.startswith('$G') and len(line) > 6: # 简单的NMEA检查
                                        # 这里应该有一个NMEA解析器，为了简化，我们直接转发原始数据或简单的解析
                                        # 假设我们只关心GGA或RMC
                                        # 这里为了保持接口一致性，我们需要解析它
                                        # 由于没有引入pynmea2，我们手动做简单解析或仅转发原始NMEA作为payload
                                        # SDK output type is gps.fix, expecting dict.
                                        # For now, let's just forward the raw line in a dict wrapper if we don't want to write a full parser
                                        # But the output port description says "RTK GPS positioning data output", usually parsed.
                                        # Let's implement a very simple parser for GPGGA
                                        
                                        parts = line.split(',')
                                        if 'GGA' in parts[0] and len(parts) > 9:
                                            try:
                                                lat = float(parts[2]) if parts[2] else 0.0
                                                # Convert DDMM.MMMMM to DD.DDDDD
                                                lat_deg = int(lat / 100)
                                                lat_min = lat - lat_deg * 100
                                                lat = lat_deg + lat_min / 60
                                                if parts[3] == 'S': lat = -lat
                                                
                                                lon = float(parts[4]) if parts[4] else 0.0
                                                lon_deg = int(lon / 100)
                                                lon_min = lon - lon_deg * 100
                                                lon = lon_deg + lon_min / 60
                                                if parts[5] == 'W': lon = -lon
                                                
                                                fix_quality = int(parts[6]) if parts[6] else 0
                                                num_sats = int(parts[7]) if parts[7] else 0
                                                alt = float(parts[9]) if parts[9] else 0.0
                                                
                                                fix_type_map = {0: 'INVALID', 1: 'GPS', 2: 'DGPS', 4: 'RTK', 5: 'RTK_FLOAT'}
                                                
                                                gps_data = {
                                                    'seq': sequence,
                                                    'timestamp': time.time(),
                                                    'latitude': lat,
                                                    'longitude': lon,
                                                    'altitude': alt,
                                                    'fix_type': fix_type_map.get(fix_quality, 'UNKNOWN'),
                                                    'num_satellites': num_sats,
                                                    'raw_nmea': line
                                                }
                                                output_port.send(gps_data)
                                                sequence += 1
                                            except ValueError:
                                                pass
                            except Exception as e:
                                sdk.logger.error(f"Serial read error: {e}")
                                time.sleep(1.0) # wait before retry
                        else:
                            # Try to reconnect
                            try:
                                if serial_conn: serial_conn.close()
                                serial_conn = serial.Serial(
                                    port=device,
                                    baudrate=baudrate,
                                    timeout=0.1
                                )
                                sdk.logger.info(f"Reconnected to {device}")
                            except Exception as e:
                                sdk.logger.error(f"Reconnection failed: {e}")
                                time.sleep(1.0)
                        
                        # Serial reading is blocking/event driven, no sleep needed if we use blocking read with timeout
                        # But we used timeout=0.1, so it's fine.


            except KeyboardInterrupt:
                sdk.logger.info("Received interrupt signal, shutting down...")

    except Exception as e:
        die(f"Fatal error: {e}")


if __name__ == '__main__':
    main()
