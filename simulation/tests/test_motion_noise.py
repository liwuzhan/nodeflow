#!/usr/bin/env python3
"""
测试运动噪声模型

验证：
1. 打滑噪声正确应用（线速度只能减少，角速度双向变化）
2. 不同的打滑比例产生不同的结果
3. 速度控制模式工作正确
4. 油门/转向模式仍然工作
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from physics import KinematicsEngine
from state import RobotState
import statistics


def test_slip_characteristics():
    """测试打滑特性"""
    print("=" * 60)
    print("测试1：打滑特性验证")
    print("=" * 60)

    # 创建运动学引擎
    engine = KinematicsEngine(
        dt=0.01,
        max_speed=2.0,
        slip_ratio=0.05,  # 5%
        enable_slip=True
    )

    # 测试：线速度应该只减少或保持
    print("\n测试1.1：线速度打滑（应该只减少）")
    print("-" * 60)
    linear_vel = 1.0  # m/s
    angular_vel = 0.0  # rad/s

    velocity_changes = []
    for i in range(10):
        v_real, w_real = engine.apply_slip_noise(linear_vel, angular_vel)
        change = v_real - linear_vel
        velocity_changes.append(v_real)
        print(f"循环 {i+1}: 期望速度={linear_vel:.4f} m/s, 实际速度={v_real:.4f} m/s, "
              f"变化={change:.4f} m/s")

        # 验证：线速度只能减少
        if v_real > linear_vel:
            print(f"  ❌ 错误：线速度增加了！")
        elif v_real < linear_vel:
            print(f"  ✓ 正确：线速度减少")
        else:
            print(f"  ✓ 正确：线速度无变化")

    # 统计
    avg_velocity = statistics.mean(velocity_changes)
    min_velocity = min(velocity_changes)
    max_velocity = max(velocity_changes)
    print(f"\n统计: 平均={avg_velocity:.4f}, 最小={min_velocity:.4f}, 最大={max_velocity:.4f}")

    # 测试：角速度应该双向变化
    print("\n测试1.2：角速度打滑（应该双向变化）")
    print("-" * 60)
    linear_vel = 1.0  # m/s
    angular_vel = 0.5  # rad/s

    angular_changes = []
    for i in range(10):
        v_real, w_real = engine.apply_slip_noise(linear_vel, angular_vel)
        change = w_real - angular_vel
        angular_changes.append(change)
        print(f"循环 {i+1}: 期望角速度={angular_vel:.4f} rad/s, 实际={w_real:.4f} rad/s, "
              f"变化={change:.4f} rad/s")

    # 统计
    positive_changes = sum(1 for c in angular_changes if c > 0)
    negative_changes = sum(1 for c in angular_changes if c < 0)
    print(f"\n统计: 正向变化={positive_changes}次, 负向变化={negative_changes}次")


def test_speed_dependent_slip():
    """测试速度相关的打滑"""
    print("\n" + "=" * 60)
    print("测试2：速度相关的打滑")
    print("=" * 60)

    # 创建运动学引擎
    engine = KinematicsEngine(
        dt=0.01,
        max_speed=2.0,
        slip_ratio=0.05,  # 5%
        enable_slip=True
    )

    speeds = [0.2, 0.5, 1.0, 1.5, 2.0]  # m/s
    print("\n线速度打滑随速度变化:")
    print("-" * 60)

    for speed in speeds:
        slip_losses = []
        for _ in range(100):
            v_real, _ = engine.apply_slip_noise(speed, 0.0)
            slip_losses.append(speed - v_real)

        avg_loss = statistics.mean(slip_losses)
        loss_percentage = (avg_loss / speed * 100) if speed > 0 else 0
        print(f"速度 {speed:.1f} m/s: 平均打滑={avg_loss:.4f} m/s ({loss_percentage:.2f}%)")


def test_disabled_slip():
    """测试禁用打滑时速度保持不变"""
    print("\n" + "=" * 60)
    print("测试3：禁用打滑（速度应该保持不变）")
    print("=" * 60)

    # 创建无打滑的运动学引擎
    engine = KinematicsEngine(
        dt=0.01,
        max_speed=2.0,
        slip_ratio=0.05,
        enable_slip=False  # 禁用打滑
    )

    linear_vel = 1.0
    angular_vel = 0.5

    print("\n运行10次，验证速度保持不变:")
    print("-" * 60)

    all_same = True
    for i in range(10):
        v_real, w_real = engine.apply_slip_noise(linear_vel, angular_vel)
        match_linear = "✓" if abs(v_real - linear_vel) < 1e-10 else "❌"
        match_angular = "✓" if abs(w_real - angular_vel) < 1e-10 else "❌"
        print(f"循环 {i+1}: v={v_real:.4f} {match_linear}, ω={w_real:.4f} {match_angular}")

        if abs(v_real - linear_vel) > 1e-10 or abs(w_real - angular_vel) > 1e-10:
            all_same = False

    if all_same:
        print("\n✓ 正确：禁用打滑时，速度保持完全相同")
    else:
        print("\n❌ 错误：禁用打滑时，速度发生了变化！")


def test_velocity_control_mode():
    """测试速度控制模式"""
    print("\n" + "=" * 60)
    print("测试4：速度控制模式")
    print("=" * 60)

    engine = KinematicsEngine(
        dt=0.01,
        max_speed=2.0,
        slip_ratio=0.05,
        enable_slip=True
    )

    state = RobotState()
    state.x = 0.0
    state.y = 0.0
    state.yaw = 0.0
    state.vx = 0.0

    print("\n设置速度控制: v=1.0 m/s, ω=0.1 rad/s")
    print("-" * 60)

    engine.set_velocity_control(1.0, 0.1)

    # 模拟10步
    for i in range(10):
        state = engine._step_velocity_control(state)
        print(f"步骤 {i+1}: x={state.x:.4f}, y={state.y:.4f}, yaw={state.yaw:.4f}, "
              f"vx={state.vx:.4f}, ω={state.omega_yaw:.4f}")

    print(f"\n最终位置: ({state.x:.4f}, {state.y:.4f})")
    print(f"最终姿态: yaw={state.yaw:.4f}")


def test_throttle_control_mode():
    """测试油门/转向模式（向后兼容）"""
    print("\n" + "=" * 60)
    print("测试5：油门/转向模式（向后兼容）")
    print("=" * 60)

    engine = KinematicsEngine(
        dt=0.01,
        max_speed=2.0,
        slip_ratio=0.05,
        enable_slip=True
    )

    state = RobotState()
    state.x = 0.0
    state.y = 0.0
    state.yaw = 0.0
    state.vx = 0.0

    print("\n设置油门/转向: throttle=0.5, steering=0.2")
    print("-" * 60)

    engine.set_control(0.5, 0.2)

    # 模拟5步加速
    for i in range(5):
        state = engine._step_throttle_control(state)
        print(f"步骤 {i+1}: vx={state.vx:.4f}, yaw={state.yaw:.4f}")

    print(f"\n达到的速度: {state.vx:.4f} m/s (目标: {0.5 * 2.0:.4f} m/s)")


def test_control_mode_switching():
    """测试控制模式切换"""
    print("\n" + "=" * 60)
    print("测试6：控制模式自动切换")
    print("=" * 60)

    engine = KinematicsEngine(
        dt=0.01,
        max_speed=2.0,
        slip_ratio=0.05,
        enable_slip=True
    )

    state = RobotState()

    print("\n步骤1: 使用速度控制模式")
    engine.set_velocity_control(1.0, 0.1)
    state = engine.step(state)
    print(f"状态: vx={state.vx:.4f}, ω={state.omega_yaw:.4f} (使用速度模式)")

    print("\n步骤2: 切换到油门/转向模式")
    engine.set_control(0.5, 0.0)
    engine.set_velocity_control(0.0, 0.0)  # 清除速度控制
    state = engine.step(state)
    print(f"状态: vx={state.vx:.4f} (使用油门模式)")

    print("\n步骤3: 回到速度控制模式")
    engine.set_velocity_control(0.8, 0.05)
    state = engine.step(state)
    print(f"状态: vx={state.vx:.4f}, ω={state.omega_yaw:.4f} (使用速度模式)")


if __name__ == "__main__":
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║         运动噪声模型测试套件                              ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    test_slip_characteristics()
    test_speed_dependent_slip()
    test_disabled_slip()
    test_velocity_control_mode()
    test_throttle_control_mode()
    test_control_mode_switching()

    print("\n" + "=" * 60)
    print("所有测试完成")
    print("=" * 60)
