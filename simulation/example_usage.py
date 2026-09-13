#!/usr/bin/env python3
"""
仿真器使用示例

展示如何在农田作业场景中使用仿真器：
1. 获取田地信息
2. 模拟简单的覆盖作业
3. 读取RTK GPS定位
4. 记录覆盖轨迹
"""

import zmq
import json
import time
import math


class FarmSimulatorClient:
    """农田仿真器客户端"""

    def __init__(self, port: int = 5555):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(f"tcp://localhost:{port}")

    def request(self, data: dict) -> dict:
        """发送请求"""
        self.socket.send_json(data)
        return self.socket.recv_json()

    def get_field(self) -> dict:
        """获取田地信息"""
        return self.request({"type": "get_field"})["field"]

    def set_velocity(self, linear: float, angular: float):
        """设置速度（带打滑）"""
        return self.request({
            "type": "set_actuator",
            "actuator": "velocity",
            "data": {
                "linear_velocity": linear,
                "angular_velocity": angular
            }
        })

    def get_rtk(self) -> dict:
        """获取RTK定位"""
        resp = self.request({"type": "get_sensor", "sensor": "rtk_gps"})
        return resp.get("data")

    def get_position(self) -> tuple:
        """获取当前位置"""
        resp = self.request({"type": "get_state"})
        pos = resp["state"]["position"]
        return (pos["x"], pos["y"], resp["state"]["orientation"]["yaw"])

    def reset(self):
        """重置仿真"""
        return self.request({"type": "reset"})

    def close(self):
        """关闭连接"""
        self.socket.close()
        self.context.term()


def simple_coverage_pattern(field_width: float, field_length: float,
                            swath_width: float = 2.0):
    """
    生成简单的往返覆盖模式

    Args:
        field_width: 田地宽度（米）
        field_length: 田地长度（米）
        swath_width: 作业幅宽（米）

    Returns:
        路径点列表 [(x, y, yaw), ...]
    """
    path = []
    y = 0
    direction = 1  # 1: 向右, -1: 向左

    while y < field_length:
        if direction == 1:
            # 向右
            path.append((0, y, 0))
            path.append((field_width, y, 0))
        else:
            # 向左
            path.append((field_width, y, math.pi))
            path.append((0, y, math.pi))

        # 移动到下一行
        y += swath_width
        direction *= -1

        if y < field_length:
            # 转向
            if direction == 1:
                path.append((0, y, 0))
            else:
                path.append((field_width, y, math.pi))

    return path


def pure_pursuit_control(current_pos: tuple, target_pos: tuple,
                         lookahead: float = 2.0, max_speed: float = 1.0):
    """
    简单的纯追踪控制

    Args:
        current_pos: 当前位置 (x, y, yaw)
        target_pos: 目标位置 (x, y, yaw)
        lookahead: 前瞻距离
        max_speed: 最大速度

    Returns:
        (linear_vel, angular_vel)
    """
    cx, cy, cyaw = current_pos
    tx, ty, _ = target_pos

    # 计算到目标的距离和角度
    dx = tx - cx
    dy = ty - cy
    distance = math.sqrt(dx**2 + dy**2)

    if distance < 0.1:  # 到达目标点
        return 0.0, 0.0

    # 目标角度
    target_yaw = math.atan2(dy, dx)

    # 角度差
    yaw_error = target_yaw - cyaw
    # 归一化到 [-pi, pi]
    while yaw_error > math.pi:
        yaw_error -= 2 * math.pi
    while yaw_error < -math.pi:
        yaw_error += 2 * math.pi

    # 简单的P控制
    linear_vel = max_speed if abs(yaw_error) < 0.5 else max_speed * 0.5
    angular_vel = 2.0 * yaw_error  # 比例增益 = 2.0

    # 限制角速度
    angular_vel = max(-1.0, min(1.0, angular_vel))

    return linear_vel, angular_vel


def run_coverage_simulation():
    """运行覆盖作业仿真"""
    print("=" * 60)
    print("农田覆盖作业仿真示例")
    print("=" * 60)

    # 连接仿真器
    client = FarmSimulatorClient()

    try:
        # 1. 获取田地信息
        print("\n1. 获取田地信息...")
        field = client.get_field()
        print(f"   田地类型: {field['type']}")
        print(f"   尺寸: {field['width']}m x {field['length']}m")
        print(f"   面积: {field['area']:.0f} m²")

        # 2. 生成覆盖路径
        print("\n2. 生成覆盖路径...")
        swath_width = 2.0  # 2米幅宽
        path = simple_coverage_pattern(field['width'], field['length'], swath_width)
        print(f"   路径点数: {len(path)}")
        print(f"   预计覆盖行数: {len(path) // 2}")

        # 3. 重置仿真
        print("\n3. 重置仿真...")
        client.reset()
        time.sleep(0.1)

        # 4. 执行作业
        print("\n4. 开始作业...")
        print("   (仅模拟前3个路径点)")

        trajectory = []  # 记录轨迹

        for i in range(min(3, len(path))):
            target = path[i]
            print(f"\n   → 目标点 {i+1}/{min(3, len(path))}: ({target[0]:.1f}, {target[1]:.1f})")

            # 向目标点移动
            reached = False
            step_count = 0
            max_steps = 100  # 最多100步

            while not reached and step_count < max_steps:
                # 获取当前位置
                current = client.get_position()

                # 计算控制指令
                v, omega = pure_pursuit_control(current, target, lookahead=2.0, max_speed=1.0)

                # 发送控制指令
                client.set_velocity(v, omega)

                # 记录轨迹
                trajectory.append(current)

                # 检查是否到达
                dx = target[0] - current[0]
                dy = target[1] - current[1]
                distance = math.sqrt(dx**2 + dy**2)

                if distance < 0.5:  # 0.5米容差
                    reached = True
                    print(f"     ✓ 到达! 位置: ({current[0]:.2f}, {current[1]:.2f}), "
                          f"步数: {step_count}")

                step_count += 1
                time.sleep(0.05)  # 50ms控制周期

            if not reached:
                print(f"     ⚠ 未能在{max_steps}步内到达")

        # 停止
        client.set_velocity(0.0, 0.0)

        # 5. 统计结果
        print("\n5. 作业统计...")
        print(f"   轨迹点数: {len(trajectory)}")
        print(f"   总距离: {sum(math.sqrt((trajectory[i+1][0]-trajectory[i][0])**2 + (trajectory[i+1][1]-trajectory[i][1])**2) for i in range(len(trajectory)-1)):.2f} m")

        # 6. 采样RTK精度
        print("\n6. RTK定位采样（5次）...")
        for i in range(5):
            rtk = client.get_rtk()
            if rtk:
                print(f"   采样{i+1}: {rtk['rtk_status']:6s} - "
                      f"精度 {rtk['accuracy_h']:.4f}m, "
                      f"卫星 {rtk['num_satellites']}颗")
            time.sleep(0.06)  # 稍大于50ms（20Hz）

        print("\n✓ 仿真完成")

    finally:
        client.close()


def run_slip_test():
    """运行打滑测试"""
    print("\n" + "=" * 60)
    print("打滑效果测试")
    print("=" * 60)

    client = FarmSimulatorClient()

    try:
        print("\n测试不同速度的打滑效果...")
        client.reset()
        time.sleep(0.1)

        speeds = [0.5, 1.0, 1.5, 2.0]

        for speed in speeds:
            print(f"\n目标速度: {speed:.1f} m/s")

            # 设置速度
            client.set_velocity(speed, 0.0)
            time.sleep(0.1)  # 等待稳定

            # 采样10次
            velocities = []
            for _ in range(10):
                pos = client.get_position()
                state = client.request({"type": "get_state"})["state"]
                vx = state["velocity"]["vx"]
                velocities.append(vx)
                time.sleep(0.02)

            # 统计
            import statistics
            avg_v = statistics.mean(velocities)
            slip_pct = ((speed - avg_v) / speed) * 100 if speed > 0 else 0

            print(f"  实际平均速度: {avg_v:.4f} m/s")
            print(f"  打滑: {slip_pct:.2f}%")

        # 停止
        client.set_velocity(0.0, 0.0)

    finally:
        client.close()


def main():
    """主函数"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║     农田仿真器使用示例                                    ║")
    print("╚════════════════════════════════════════════════════════════╝")

    print("\n请确保仿真器服务器正在运行:")
    print("  python3 server.py")
    print("")

    input("按Enter继续...")

    try:
        # 示例1: 覆盖作业
        run_coverage_simulation()

        # 示例2: 打滑测试
        run_slip_test()

        print("\n" + "=" * 60)
        print("所有示例完成")
        print("=" * 60)

    except zmq.error.Again:
        print("\n❌ 错误: 无法连接到仿真器")
        print("   请确保运行: python3 server.py")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
