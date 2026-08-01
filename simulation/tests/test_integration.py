#!/usr/bin/env python3
"""
仿真器集成测试

测试完整的农田作业仿真流程：
1. 启动仿真器服务器
2. 获取田地信息
3. 设置速度控制（带打滑）
4. 读取RTK GPS数据（20Hz频率限制）
5. 验证打滑效果和RTK精度
"""

import sys
import time
import zmq
import json
import subprocess
import signal
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


class SimulatorClient:
    """仿真器客户端"""

    def __init__(self, port: int = 5555, timeout: int = 5000):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout)  # 5秒接收超时
        self.socket.setsockopt(zmq.LINGER, 0)  # 关闭时不等待
        self.socket.connect(f"tcp://localhost:{port}")

    def send_request(self, request: dict) -> dict:
        """发送请求并接收响应"""
        self.socket.send_json(request)
        return self.socket.recv_json()

    def get_field(self) -> dict:
        """获取田地信息"""
        return self.send_request({"type": "get_field"})

    def get_sensor(self, sensor_type: str) -> dict:
        """获取传感器数据"""
        return self.send_request({
            "type": "get_sensor",
            "sensor": sensor_type
        })

    def set_velocity(self, linear_vel: float, angular_vel: float) -> dict:
        """设置速度控制"""
        return self.send_request({
            "type": "set_actuator",
            "actuator": "velocity",
            "data": {
                "linear_velocity": linear_vel,
                "angular_velocity": angular_vel
            }
        })

    def get_state(self) -> dict:
        """获取仿真状态"""
        return self.send_request({"type": "get_state"})

    def reset(self) -> dict:
        """重置仿真"""
        return self.send_request({"type": "reset"})

    def close(self):
        """关闭连接"""
        self.socket.close()
        self.context.term()


def test_field_generation():
    """测试1：田地生成"""
    print("\n" + "=" * 60)
    print("测试1：田地生成")
    print("=" * 60)

    client = SimulatorClient()

    try:
        response = client.get_field()
        if response["status"] != "ok":
            print(f"❌ 错误: {response.get('message')}")
            return False

        field = response["field"]
        print(f"\n田地类型: {field['type']}")
        print(f"尺寸: {field['width']}m x {field['length']}m")
        print(f"面积: {field['area']:.2f} m²")
        print(f"边界点数: {len(field['boundary'])}")
        print(f"障碍物数量: {len(field['obstacles'])}")
        print(f"入口点: {field['entry_points']}")

        # 验证边界
        if field['type'] == 'rectangular':
            if len(field['boundary']) != 4:
                print(f"❌ 错误: 矩形应有4个顶点，实际{len(field['boundary'])}个")
                return False
            print("✓ 矩形田地边界正确")
        else:
            print(f"✓ 不规则田地，{len(field['boundary'])}个顶点")

        return True

    finally:
        client.close()


def test_velocity_control_with_slip():
    """测试2：速度控制与打滑"""
    print("\n" + "=" * 60)
    print("测试2：速度控制与打滑")
    print("=" * 60)

    client = SimulatorClient()

    try:
        # 重置仿真
        client.reset()
        print("\n仿真已重置")

        # 设置恒定速度
        target_linear_vel = 1.0  # m/s
        target_angular_vel = 0.0  # rad/s

        print(f"\n设置目标速度: v={target_linear_vel} m/s, ω={target_angular_vel} rad/s")
        response = client.set_velocity(target_linear_vel, target_angular_vel)

        if response["status"] != "ok":
            print(f"❌ 错误: {response.get('message')}")
            return False

        print("✓ 速度控制设置成功")

        # 等待几个时间步让速度生效
        time.sleep(0.1)

        # 读取多个状态，观察打滑效果
        print("\n观察打滑效果（10次采样）:")
        print("-" * 60)

        actual_velocities = []
        for i in range(10):
            state_response = client.get_state()
            if state_response["status"] != "ok":
                print(f"❌ 错误: {state_response.get('message')}")
                return False

            state = state_response["state"]
            vx = state["vx"]
            actual_velocities.append(vx)

            # 验证打滑特性：实际速度应该 <= 目标速度
            if vx > target_linear_vel + 0.001:  # 允许小误差
                print(f"  步骤{i+1}: vx={vx:.4f} m/s ❌ (超过目标速度)")
                return False
            else:
                slip_amount = target_linear_vel - vx
                slip_percentage = (slip_amount / target_linear_vel * 100) if target_linear_vel > 0 else 0
                print(f"  步骤{i+1}: vx={vx:.4f} m/s, 打滑={slip_amount:.4f} m/s ({slip_percentage:.2f}%)")

            time.sleep(0.02)  # 20ms间隔

        # 统计打滑
        import statistics
        avg_velocity = statistics.mean(actual_velocities)
        avg_slip = target_linear_vel - avg_velocity
        avg_slip_percentage = (avg_slip / target_linear_vel * 100)

        print(f"\n打滑统计:")
        print(f"  平均速度: {avg_velocity:.4f} m/s")
        print(f"  平均打滑: {avg_slip:.4f} m/s ({avg_slip_percentage:.2f}%)")
        print(f"  最小速度: {min(actual_velocities):.4f} m/s")
        print(f"  最大速度: {max(actual_velocities):.4f} m/s")

        # 验证打滑在合理范围内（0-5%）
        if 0 <= avg_slip_percentage <= 6:  # 允许略超5%
            print("✓ 打滑效果符合预期")
            return True
        else:
            print(f"❌ 打滑效果异常: {avg_slip_percentage:.2f}%")
            return False

    finally:
        client.close()


def test_rtk_frequency_limiting():
    """测试3：RTK频率限制（20Hz）"""
    print("\n" + "=" * 60)
    print("测试3：RTK频率限制（20Hz）")
    print("=" * 60)

    client = SimulatorClient()

    try:
        # 重置仿真
        client.reset()
        time.sleep(0.1)

        print("\n快速请求RTK数据（应该被限制到20Hz）:")
        print("-" * 60)

        request_count = 0
        success_count = 0
        limited_count = 0

        start_time = time.time()
        test_duration = 1.0  # 1秒测试

        while time.time() - start_time < test_duration:
            response = client.get_sensor("rtk_gps")
            request_count += 1

            if response["status"] == "ok":
                if response["data"] is not None:
                    success_count += 1
                    rtk_data = response["data"]
                    print(f"  请求{request_count}: ✓ RTK数据 - 状态={rtk_data.get('rtk_status')}, "
                          f"精度={rtk_data.get('accuracy_h'):.4f}m")
                else:
                    limited_count += 1
                    # print(f"  请求{request_count}: - 频率限制 - {response.get('note')}")

            time.sleep(0.01)  # 10ms间隔（100Hz请求）

        elapsed_time = time.time() - start_time
        actual_rate = success_count / elapsed_time

        print(f"\n统计:")
        print(f"  总请求数: {request_count}")
        print(f"  成功返回: {success_count}")
        print(f"  频率限制: {limited_count}")
        print(f"  测试时长: {elapsed_time:.2f}s")
        print(f"  实际速率: {actual_rate:.1f} Hz")

        # 验证频率接近20Hz（允许±2Hz误差）
        if 18 <= actual_rate <= 22:
            print(f"✓ RTK频率限制正确 ({actual_rate:.1f} Hz ≈ 20 Hz)")
            return True
        else:
            print(f"❌ RTK频率异常: {actual_rate:.1f} Hz")
            return False

    finally:
        client.close()


def test_rtk_precision_levels():
    """测试4：RTK精度等级"""
    print("\n" + "=" * 60)
    print("测试4：RTK精度等级分布")
    print("=" * 60)

    client = SimulatorClient()

    try:
        # 重置仿真
        client.reset()
        time.sleep(0.1)

        print("\n采样100次RTK数据，统计精度分布:")
        print("-" * 60)

        status_counts = {
            "FIXED": 0,
            "FLOAT": 0,
            "SINGLE": 0,
            "NONE": 0
        }

        sample_count = 100
        for i in range(sample_count):
            response = client.get_sensor("rtk_gps")

            if response["status"] == "ok" and response["data"]:
                rtk_data = response["data"]
                status = rtk_data.get("rtk_status", "UNKNOWN")
                if status in status_counts:
                    status_counts[status] += 1

            time.sleep(0.06)  # 稍大于50ms，确保每次都能获取新数据

        print(f"\nRTK状态分布:")
        for status, count in status_counts.items():
            percentage = (count / sample_count) * 100
            expected = {
                "FIXED": 85,
                "FLOAT": 10,
                "SINGLE": 4,
                "NONE": 1
            }[status]
            print(f"  {status:8s}: {count:3d} ({percentage:5.1f}%) - 预期约{expected}%")

        # 验证FIXED状态占主导（应该在70-95%之间）
        fixed_percentage = (status_counts["FIXED"] / sample_count) * 100
        if 70 <= fixed_percentage <= 95:
            print(f"\n✓ RTK状态分布合理 (FIXED = {fixed_percentage:.1f}%)")
            return True
        else:
            print(f"\n❌ RTK状态分布异常 (FIXED = {fixed_percentage:.1f}%)")
            return False

    finally:
        client.close()


def main():
    """主测试函数"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║         仿真器集成测试套件                                ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # 等待仿真器启动
    print("\n⏳ 等待仿真器启动...")
    time.sleep(2)

    # 运行测试
    tests = [
        ("田地生成", test_field_generation),
        ("速度控制与打滑", test_velocity_control_with_slip),
        ("RTK频率限制", test_rtk_frequency_limiting),
        ("RTK精度等级", test_rtk_precision_levels),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = 0
    failed = 0
    for test_name, success in results:
        status = "✓ 通过" if success else "❌ 失败"
        print(f"  {test_name:30s} {status}")
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\n总计: {passed}通过, {failed}失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
