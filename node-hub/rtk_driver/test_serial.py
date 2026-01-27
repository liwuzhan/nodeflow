#!/usr/bin/env python3
"""
RTK串口连接测试脚本

用于快速验证RTK设备连接和数据输出
"""

import sys
import time
from device_interface import SerialInterface
from nmea_parser import NMEAParser


def test_serial_connection(port: str = "/dev/ttyUSB0", baudrate: int = 115200):
    """
    测试串口连接和NMEA数据解析

    Args:
        port: 串口设备路径
        baudrate: 波特率
    """
    print("=" * 60)
    print("RTK串口连接测试")
    print("=" * 60)
    print(f"串口: {port}")
    print(f"波特率: {baudrate}")
    print()

    # 创建串口接口
    serial = SerialInterface(port, baudrate, timeout=1.0)

    # 连接
    print("正在连接...")
    if not serial.connect():
        print("❌ 连接失败！")
        print()
        print("可能原因：")
        print("  1. 串口设备不存在")
        print("  2. 权限不足（运行：sudo chmod 666 /dev/ttyUSB0）")
        print("  3. 设备已被其他程序占用")
        print("  4. 波特率不匹配")
        return False

    print("✓ 连接成功")
    print()

    # 创建解析器
    parser = NMEAParser()

    # 读取数据
    print("正在读取NMEA数据（10秒）...")
    print("按 Ctrl+C 提前停止")
    print("-" * 60)

    start_time = time.time()
    message_count = 0
    valid_count = 0
    checksum_errors = 0
    parse_errors = 0

    message_types = {}

    try:
        while time.time() - start_time < 10.0:
            # 读取一行
            line = serial.read_line(timeout=0.5)

            if not line:
                continue

            message_count += 1

            # 显示原始数据（前3条）
            if message_count <= 3:
                print(f"[{message_count}] {line}")

            # 验证校验和
            if not parser.validate_checksum(line):
                checksum_errors += 1
                continue

            # 解析消息
            data = parser.parse(line)

            if data:
                valid_count += 1
                msg_type = data.get('message_type', 'UNKNOWN')
                message_types[msg_type] = message_types.get(msg_type, 0) + 1

                # 显示第一条有效数据
                if valid_count == 1:
                    print()
                    print("✓ 第一条有效数据:")
                    print(f"  消息类型: {msg_type}")
                    if 'lat' in data and 'lon' in data:
                        print(f"  位置: ({data['lat']:.8f}, {data['lon']:.8f})")
                    if 'alt' in data:
                        print(f"  海拔: {data['alt']:.2f} m")
                    if 'heading' in data:
                        import math
                        heading_deg = math.degrees(data['heading'])
                        print(f"  航向: {heading_deg:.2f}°")
                    if 'rtk_quality' in data:
                        quality_names = {0: "无效", 1: "单点", 2: "浮点", 3: "固定"}
                        quality = data['rtk_quality']
                        print(f"  RTK质量: {quality_names.get(quality, '未知')} ({quality})")
                    if 'num_satellites' in data:
                        print(f"  卫星数: {data['num_satellites']}")
                    print()
            else:
                parse_errors += 1

    except KeyboardInterrupt:
        print("\n用户中断")

    # 断开连接
    serial.disconnect()

    # 统计结果
    print("-" * 60)
    print()
    print("测试结果：")
    print(f"  运行时间: {time.time() - start_time:.1f} 秒")
    print(f"  总消息数: {message_count}")
    print(f"  有效消息: {valid_count}")
    print(f"  校验和错误: {checksum_errors}")
    print(f"  解析错误: {parse_errors}")
    print()

    if message_types:
        print("消息类型统计：")
        for msg_type, count in message_types.items():
            print(f"  {msg_type}: {count} 条")
        print()

    # 评估
    if valid_count == 0:
        print("❌ 测试失败：未收到有效数据")
        print()
        print("可能原因：")
        print("  1. RTK设备未配置NMEA输出")
        print("  2. 波特率不匹配")
        print("  3. RTK设备未启动")
        return False

    elif valid_count < 10:
        print("⚠️  警告：有效数据较少")
        print()
        print("建议检查：")
        print("  1. 设备连接稳定性")
        print("  2. NMEA消息输出频率")
        return True

    else:
        print("✓ 测试成功！RTK设备工作正常")
        print()
        print("下一步：")
        print("  1. 运行完整测试：python3 -m runtime.main examples/rtk_test.yaml")
        print("  2. 查看文档：cat node-hub/rtk_driver/README.md")
        return True


def main():
    """主函数"""
    # 解析命令行参数
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    try:
        success = test_serial_connection(port, baudrate)
        sys.exit(0 if success else 1)

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print()
    print("用法: python3 test_serial.py [串口] [波特率]")
    print("示例: python3 test_serial.py /dev/ttyUSB0 115200")
    print()

    main()
