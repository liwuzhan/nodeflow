#!/usr/bin/env python3
"""
测试地面不平导致的角速度偏移

验证：
1. 即使指令角速度为0，也会存在偏移
2. 偏移的长期平均为0
3. 瞬时值在合理范围内
"""

import sys
import math
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from state import RobotState
from physics import KinematicsEngine


def test_terrain_noise_basic():
    """测试1: 基础地面噪声特性"""
    print("\n" + "="*70)
    print("测试1: 基础地面噪声特性")
    print("="*70)

    # 创建运动学引擎，启用地面噪声
    engine = KinematicsEngine(
        dt=0.01,
        terrain_roughness=0.02,  # 2cm/s 角速度偏移
        enable_terrain_noise=True
    )

    state = RobotState()
    noise_samples = []

    print("\n采样100步，每步10ms...")
    print("指令: 线速度=1.0m/s, 角速度=0.0rad/s (直线前进)\n")

    for i in range(100):
        # 设置直线前进指令（角速度为0）
        engine.set_velocity_control(1.0, 0.0)

        # 更新噪声
        engine.update_terrain_noise()

        # 记录噪声值
        noise_samples.append(engine.terrain_noise_omega)

        # 执行一步仿真
        state = engine.step(state)

        # 显示部分采样
        if i % 10 == 0:
            noise_deg = math.degrees(engine.terrain_noise_omega)
            print(f"  步{i:3d}: terrain_noise = {engine.terrain_noise_omega:+.6f} rad/s "
                  f"({noise_deg:+.3f} 度/秒)")

    # 统计分析
    print("\n" + "-"*70)
    print("统计分析:")
    print("-"*70)

    noise_mean = sum(noise_samples) / len(noise_samples)
    noise_std = math.sqrt(sum((x - noise_mean)**2 for x in noise_samples) / len(noise_samples))
    noise_min = min(noise_samples)
    noise_max = max(noise_samples)

    print(f"噪声均值: {noise_mean:+.6f} rad/s ({math.degrees(noise_mean):+.3f} 度/秒)")
    print(f"噪声标准差: {noise_std:.6f} rad/s ({math.degrees(noise_std):.3f} 度/秒)")
    print(f"噪声范围: [{noise_min:+.6f}, {noise_max:+.6f}] rad/s")
    print(f"           ([{math.degrees(noise_min):+.3f}, {math.degrees(noise_max):+.3f}] 度/秒)")

    # 验证
    print("\n" + "-"*70)
    print("验证:")
    print("-"*70)

    checks = [
        ("噪声均值接近0（|均值| < 0.005）", abs(noise_mean) < 0.005),
        ("噪声非零（标准差 > 0.001）", noise_std > 0.001),
        ("噪声在合理范围（最大偏移 < 0.05 rad/s）", abs(noise_max) < 0.05 and abs(noise_min) < 0.05),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "✓" if passed else "❌"
        print(f"{status} {check_name}")
        if not passed:
            all_passed = False

    return all_passed


def test_terrain_noise_long_term():
    """测试2: 长期均值为0"""
    print("\n" + "="*70)
    print("测试2: 长期均值为0")
    print("="*70)

    engine = KinematicsEngine(
        dt=0.01,
        terrain_roughness=0.02,
        enable_terrain_noise=True
    )

    state = RobotState()
    noise_samples = []
    cumulative_sum = 0.0

    print("\n采样1000步，验证累积和趋向0...\n")

    checkpoints = [100, 200, 500, 1000]
    for i in range(1000):
        engine.set_velocity_control(1.0, 0.0)
        engine.update_terrain_noise()

        noise = engine.terrain_noise_omega
        noise_samples.append(noise)
        cumulative_sum += noise

        state = engine.step(state)

        # 显示检查点
        if (i+1) in checkpoints:
            mean = sum(noise_samples) / len(noise_samples)
            print(f"  步{i+1:4d}: 累积和={cumulative_sum:+.6f}, "
                  f"均值={mean:+.6f} rad/s ({math.degrees(mean):+.3f} 度/秒)")

    # 最终统计
    final_mean = sum(noise_samples) / len(noise_samples)
    print(f"\n最终统计 (1000步):")
    print(f"  累积和: {cumulative_sum:+.6f}")
    print(f"  均值: {final_mean:+.6f} rad/s ({math.degrees(final_mean):+.3f} 度/秒)")

    # 验证
    print("\n" + "-"*70)
    print("验证:")
    print("-"*70)

    passed = abs(final_mean) < 0.002  # 1000步后均值应该很接近0
    status = "✓" if passed else "❌"
    print(f"{status} 长期均值接近0 (|均值| < 0.002 rad/s)")

    return passed


def test_terrain_noise_zero_velocity():
    """测试3: 即使速度为0也有噪声"""
    print("\n" + "="*70)
    print("测试3: 即使速度为0也有噪声")
    print("="*70)

    engine = KinematicsEngine(
        dt=0.01,
        terrain_roughness=0.02,
        enable_terrain_noise=True
    )

    state = RobotState()
    noise_samples = []

    print("\n采样50步，指令: 线速度=0, 角速度=0 (静止)\n")

    for i in range(50):
        # 设置静止指令
        engine.set_velocity_control(0.0, 0.0)

        # 更新噪声
        engine.update_terrain_noise()

        # 记录噪声值
        noise = engine.terrain_noise_omega
        noise_samples.append(noise)

        # 执行一步仿真
        state = engine.step(state)

        # 显示部分采样
        if i % 5 == 0:
            noise_deg = math.degrees(noise)
            print(f"  步{i:2d}: terrain_noise = {noise:+.6f} rad/s ({noise_deg:+.3f} 度/秒)")

    # 统计
    non_zero_count = sum(1 for x in noise_samples if abs(x) > 1e-6)
    print(f"\n非零噪声采样: {non_zero_count}/{len(noise_samples)}")

    # 验证
    print("\n" + "-"*70)
    print("验证:")
    print("-"*70)

    passed = non_zero_count > 40  # 大部分应该非零
    status = "✓" if passed else "❌"
    print(f"{status} 即使速度为0也有噪声 ({non_zero_count}/50 非零)")

    return passed


def test_terrain_noise_disabled():
    """测试4: 禁用噪声时应该为0"""
    print("\n" + "="*70)
    print("测试4: 禁用噪声时应该为0")
    print("="*70)

    engine = KinematicsEngine(
        dt=0.01,
        terrain_roughness=0.02,
        enable_terrain_noise=False  # 禁用
    )

    state = RobotState()

    print("\n采样20步，地面噪声禁用...\n")

    all_zero = True
    for i in range(20):
        engine.set_velocity_control(1.0, 0.0)
        engine.update_terrain_noise()

        noise = engine.terrain_noise_omega
        if abs(noise) > 1e-10:
            all_zero = False

        state = engine.step(state)

        if i % 5 == 0:
            print(f"  步{i:2d}: terrain_noise = {noise:+.6f} rad/s")

    # 验证
    print("\n" + "-"*70)
    print("验证:")
    print("-"*70)

    status = "✓" if all_zero else "❌"
    print(f"{status} 禁用噪声时所有值为0")

    return all_zero


def test_terrain_noise_impact():
    """测试5: 噪声对轨迹的影响"""
    print("\n" + "="*70)
    print("测试5: 噪声对轨迹的影响")
    print("="*70)

    print("\n对比实验：有噪声 vs 无噪声\n")

    # 场景A: 无噪声
    engine_no_noise = KinematicsEngine(
        dt=0.01,
        terrain_roughness=0.0,
        enable_terrain_noise=False
    )

    state_no_noise = RobotState()
    for i in range(100):
        engine_no_noise.set_velocity_control(1.0, 0.0)  # 直线前进
        state_no_noise = engine_no_noise.step(state_no_noise)

    # 场景B: 有噪声
    engine_with_noise = KinematicsEngine(
        dt=0.01,
        terrain_roughness=0.02,
        enable_terrain_noise=True
    )

    state_with_noise = RobotState()
    for i in range(100):
        engine_with_noise.set_velocity_control(1.0, 0.0)  # 直线前进
        state_with_noise = engine_with_noise.step(state_with_noise)

    # 对比结果
    print("1秒后 (100步 × 10ms):")
    print(f"\n无噪声:")
    print(f"  位置: ({state_no_noise.x:.6f}, {state_no_noise.y:.6f})")
    print(f"  航向: {math.degrees(state_no_noise.yaw):.3f} 度")

    print(f"\n有噪声:")
    print(f"  位置: ({state_with_noise.x:.6f}, {state_with_noise.y:.6f})")
    print(f"  航向: {math.degrees(state_with_noise.yaw):.3f} 度")

    # 计算偏差
    dx = state_with_noise.x - state_no_noise.x
    dy = state_with_noise.y - state_no_noise.y
    distance_deviation = math.sqrt(dx**2 + dy**2)
    heading_deviation = math.degrees(state_with_noise.yaw - state_no_noise.yaw)

    print(f"\n偏差:")
    print(f"  位置偏差: {distance_deviation:.6f} 米")
    print(f"  航向偏差: {heading_deviation:.3f} 度")

    # 验证
    print("\n" + "-"*70)
    print("验证:")
    print("-"*70)

    checks = [
        ("噪声导致位置偏差 (> 0.001m)", distance_deviation > 0.001),
        ("位置偏差在合理范围 (< 0.5m)", distance_deviation < 0.5),
        ("噪声导致航向偏差 (> 0.05度)", abs(heading_deviation) > 0.05),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "✓" if passed else "❌"
        print(f"{status} {check_name}")
        if not passed:
            all_passed = False

    return all_passed


def main():
    """主测试函数"""
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*20 + "地面不平噪声测试" + " "*31 + "║")
    print("╚" + "="*68 + "╝")

    results = []

    # 运行所有测试
    results.append(("基础特性", test_terrain_noise_basic()))
    results.append(("长期均值为0", test_terrain_noise_long_term()))
    results.append(("速度为0也有噪声", test_terrain_noise_zero_velocity()))
    results.append(("禁用噪声", test_terrain_noise_disabled()))
    results.append(("轨迹影响", test_terrain_noise_impact()))

    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)

    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)

    for test_name, passed in results:
        status = "✓" if passed else "❌"
        print(f"{status} {test_name}")

    print(f"\n总计: {passed_count}/{total_count} 通过")

    if passed_count == total_count:
        print("\n🎉 所有测试通过！")
        print("\n地面不平噪声特性：")
        print("  ✓ 即使角速度为0，也会有随机偏移")
        print("  ✓ 偏移的长期平均为0")
        print("  ✓ 瞬时值在合理范围内（约±1.1度/秒）")
        print("  ✓ 会对机器人轨迹产生真实的影响")
    else:
        print("\n❌ 部分测试失败")

    print("="*70 + "\n")

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
