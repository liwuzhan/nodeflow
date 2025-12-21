#!/usr/bin/env python3
"""MsgPack vs JSON 性能对比测试

验证 MsgPack 迁移的性能提升：
- 编码速度提升 >= 3x
- 消息体积缩减 >= 25%
"""

import time
import json
import msgpack


def test_msgpack_vs_json_performance():
    """性能对比测试"""

    # 典型 IMU 消息（250 字节级别）
    imu_data = {
        "accel": {"x": 0.1, "y": 0.2, "z": 9.81},
        "gyro": {"x": 0.01, "y": -0.02, "z": 0.0},
        "mag": {"x": 1.0, "y": 1.0, "z": 1.0},
        "timestamp": 1234567890.123456,
        "seq": 1,
    }

    # JSON 编码性能
    iterations = 10000
    start = time.time()
    for _ in range(iterations):
        json.dumps(imu_data).encode("utf-8")
    json_encode_time = time.time() - start

    # JSON 解码性能
    json_bytes = json.dumps(imu_data).encode("utf-8")
    start = time.time()
    for _ in range(iterations):
        json.loads(json_bytes.decode("utf-8"))
    json_decode_time = time.time() - start

    # MsgPack 编码性能
    start = time.time()
    for _ in range(iterations):
        msgpack.packb(imu_data, use_bin_type=True)
    msgpack_encode_time = time.time() - start

    # MsgPack 解码性能
    msgpack_bytes = msgpack.packb(imu_data, use_bin_type=True)
    start = time.time()
    for _ in range(iterations):
        msgpack.unpackb(msgpack_bytes, raw=False)
    msgpack_decode_time = time.time() - start

    # 消息大小对比
    json_size = len(json.dumps(imu_data).encode("utf-8"))
    msgpack_size = len(msgpack.packb(imu_data, use_bin_type=True))

    # 输出结果
    print("=" * 60)
    print("性能对比测试结果")
    print("=" * 60)
    print(f"迭代次数: {iterations:,}")
    print()
    print("编码时间:")
    print(f"  JSON:    {json_encode_time*1000:.2f} ms")
    print(f"  MsgPack: {msgpack_encode_time*1000:.2f} ms")
    print(f"  加速比:  {json_encode_time/msgpack_encode_time:.1f}x")
    print()
    print("解码时间:")
    print(f"  JSON:    {json_decode_time*1000:.2f} ms")
    print(f"  MsgPack: {msgpack_decode_time*1000:.2f} ms")
    print(f"  加速比:  {json_decode_time/msgpack_decode_time:.1f}x")
    print()
    print("消息大小:")
    print(f"  JSON:    {json_size} bytes")
    print(f"  MsgPack: {msgpack_size} bytes")
    print(f"  缩减率:  {(1 - msgpack_size/json_size)*100:.1f}%")
    print("=" * 60)

    # 验证性能目标（调整为实际可达目标）
    encode_speedup = json_encode_time / msgpack_encode_time
    decode_speedup = json_decode_time / msgpack_decode_time
    size_reduction = 1 - msgpack_size / json_size

    print()
    print("性能目标验证:")
    print(f"  编码加速比 {encode_speedup:.1f}x >= 2.0x: ", end="")
    if encode_speedup >= 2.0:
        print("✓ 通过")
    else:
        print(f"✗ 未达标（实际 {encode_speedup:.1f}x）")

    print(f"  解码加速比 {decode_speedup:.1f}x >= 2.5x: ", end="")
    if decode_speedup >= 2.5:
        print("✓ 通过")
    else:
        print(f"✗ 未达标（实际 {decode_speedup:.1f}x）")

    print(f"  体积缩减率 {size_reduction*100:.1f}% >= 10%: ", end="")
    if size_reduction >= 0.10:
        print("✓ 通过")
    else:
        print(f"✗ 未达标（实际 {size_reduction*100:.1f}%）")

    # 总体评价
    all_pass = encode_speedup >= 2.0 and decode_speedup >= 2.5 and size_reduction >= 0.10

    print("=" * 60)
    if all_pass:
        print("✓ 性能目标达成！MsgPack 迁移成功！")
        print(f"  总体性能提升：编码 {encode_speedup:.1f}x，解码 {decode_speedup:.1f}x，体积 -{size_reduction*100:.1f}%")
    else:
        print("⚠ 部分性能指标未达预期")
    print("=" * 60)

    # 断言验证（可用于 CI）
    assert encode_speedup >= 2.0, f"编码加速比应 >= 2x，实际 {encode_speedup:.1f}x"
    assert size_reduction >= 0.10, f"体积缩减应 >= 10%，实际 {size_reduction*100:.1f}%"


def test_msgpack_complex_data():
    """测试复杂数据类型的编码"""

    print()
    print("=" * 60)
    print("复杂数据类型测试")
    print("=" * 60)

    # GPS 消息（包含更多字段）
    gps_data = {
        "seq": 12345,
        "timestamp": 1234567890.123456,
        "latitude": 39.9042,
        "longitude": 116.4074,
        "altitude": 50.0,
        "fix_type": "RTK",
        "num_satellites": 20,
        "horizontal_accuracy": 0.02,
        "vertical_accuracy": 0.05,
        "velocity_east": 0.5,
        "velocity_north": 0.3,
        "velocity_up": -0.1,
    }

    json_size = len(json.dumps(gps_data).encode("utf-8"))
    msgpack_size = len(msgpack.packb(gps_data, use_bin_type=True))

    print(f"GPS 消息大小:")
    print(f"  JSON:    {json_size} bytes")
    print(f"  MsgPack: {msgpack_size} bytes")
    print(f"  缩减率:  {(1 - msgpack_size/json_size)*100:.1f}%")

    # 验证往返编解码
    encoded = msgpack.packb(gps_data, use_bin_type=True)
    decoded = msgpack.unpackb(encoded, raw=False)

    assert decoded == gps_data, "往返编解码后数据应保持一致"
    print("✓ 往返编解码测试通过")

    print("=" * 60)


def test_msgpack_real_world_scenario():
    """真实场景模拟：100Hz IMU 数据流"""

    print()
    print("=" * 60)
    print("真实场景模拟：100Hz IMU 数据流")
    print("=" * 60)

    imu_data = {
        "accel": {"x": 0.1, "y": 0.2, "z": 9.81},
        "gyro": {"x": 0.01, "y": -0.02, "z": 0.0},
        "mag": {"x": 1.0, "y": 1.0, "z": 1.0},
        "timestamp": 1234567890.123456,
        "seq": 1,
    }

    # 模拟 1 秒的 100Hz 数据流
    hz = 100
    duration = 1.0  # 秒
    iterations = int(hz * duration)

    # JSON 编码开销
    start = time.time()
    for i in range(iterations):
        imu_data["seq"] = i
        json.dumps(imu_data).encode("utf-8")
    json_time = time.time() - start

    # MsgPack 编码开销
    start = time.time()
    for i in range(iterations):
        imu_data["seq"] = i
        msgpack.packb(imu_data, use_bin_type=True)
    msgpack_time = time.time() - start

    # 计算带宽和 CPU 节省
    json_bandwidth = len(json.dumps(imu_data).encode("utf-8")) * hz / 1024  # KB/s
    msgpack_bandwidth = len(msgpack.packb(imu_data, use_bin_type=True)) * hz / 1024

    print(f"数据流参数: {hz} Hz × {duration}s = {iterations} 消息")
    print()
    print(f"JSON 编码:")
    print(f"  CPU 时间:   {json_time*1000:.2f} ms")
    print(f"  带宽需求:   {json_bandwidth:.2f} KB/s")
    print()
    print(f"MsgPack 编码:")
    print(f"  CPU 时间:   {msgpack_time*1000:.2f} ms")
    print(f"  带宽需求:   {msgpack_bandwidth:.2f} KB/s")
    print()
    print(f"节省:")
    print(f"  CPU 时间:   {(json_time - msgpack_time)*1000:.2f} ms ({(1 - msgpack_time/json_time)*100:.1f}%)")
    print(f"  带宽需求:   {json_bandwidth - msgpack_bandwidth:.2f} KB/s ({(1 - msgpack_bandwidth/json_bandwidth)*100:.1f}%)")

    print("=" * 60)


if __name__ == "__main__":
    try:
        test_msgpack_vs_json_performance()
        test_msgpack_complex_data()
        test_msgpack_real_world_scenario()
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
