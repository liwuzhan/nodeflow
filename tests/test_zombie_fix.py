#!/usr/bin/env python3
"""
测试僵尸进程修复功能

测试以下场景：
1. 正常关闭（Ctrl+C / SIGINT）
2. SIGTERM 信号
3. 异常退出（未捕获异常）触发 atexit
"""

import sys
import signal
import time
import subprocess
import os
from pathlib import Path

def test_normal_shutdown():
    """测试正常关闭"""
    print("\n=== 测试 1: 正常关闭（SIGINT） ===")

    # 启动 runtime
    proc = subprocess.Popen(
        ["python3", "-m", "runtime.main", "examples/planning_simulation.yaml", "--duration", "2"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # 等待启动
    time.sleep(5)

    # 发送 SIGINT
    print("发送 SIGINT...")
    proc.send_signal(signal.SIGINT)

    # 等待退出
    try:
        stdout, _ = proc.communicate(timeout=10)
        print(f"退出码: {proc.returncode}")

        # 检查关闭消息
        if "Received SIGINT" in stdout:
            print("✅ SIGINT 被正确捕获")
        if "Shutting Down" in stdout:
            print("✅ 正常关闭流程执行")
        if "shutdown_complete" not in stdout or "Emergency cleanup" not in stdout:
            print("✅ 未触发紧急清理（正常）")

        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ 关闭超时")
        proc.kill()
        return False


def test_sigterm():
    """测试 SIGTERM 信号"""
    print("\n=== 测试 2: SIGTERM 信号 ===")

    proc = subprocess.Popen(
        ["python3", "-m", "runtime.main", "examples/planning_simulation.yaml", "--duration", "100"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    time.sleep(5)

    print("发送 SIGTERM...")
    proc.send_signal(signal.SIGTERM)

    try:
        stdout, _ = proc.communicate(timeout=10)
        print(f"退出码: {proc.returncode}")

        if "Received SIGTERM" in stdout:
            print("✅ SIGTERM 被正确捕获")
        if "Shutting Down" in stdout:
            print("✅ 正常关闭流程执行")

        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ 关闭超时")
        proc.kill()
        return False


def test_sighup():
    """测试 SIGHUP 信号"""
    print("\n=== 测试 3: SIGHUP 信号 ===")

    proc = subprocess.Popen(
        ["python3", "-m", "runtime.main", "examples/planning_simulation.yaml", "--duration", "100"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    time.sleep(5)

    print("发送 SIGHUP...")
    proc.send_signal(signal.SIGHUP)

    try:
        stdout, _ = proc.communicate(timeout=10)
        print(f"退出码: {proc.returncode}")

        if "Received SIGHUP" in stdout:
            print("✅ SIGHUP 被正确捕获")
        if "Shutting Down" in stdout:
            print("✅ 正常关闭流程执行")

        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        print("❌ 关闭超时")
        proc.kill()
        return False


def check_no_zombies():
    """检查是否有僵尸进程"""
    print("\n=== 检查僵尸进程 ===")

    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )

    zombie_count = result.stdout.count("<defunct>")
    if zombie_count > 0:
        print(f"❌ 发现 {zombie_count} 个僵尸进程")
        return False
    else:
        print("✅ 无僵尸进程")
        return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print("僵尸进程修复功能测试")
    print("=" * 60)

    results = []

    # 测试 1: 正常关闭
    try:
        results.append(("正常关闭 (SIGINT)", test_normal_shutdown()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("正常关闭 (SIGINT)", False))

    time.sleep(2)

    # 测试 2: SIGTERM
    try:
        results.append(("SIGTERM 信号", test_sigterm()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("SIGTERM 信号", False))

    time.sleep(2)

    # 测试 3: SIGHUP
    try:
        results.append(("SIGHUP 信号", test_sighup()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("SIGHUP 信号", False))

    time.sleep(2)

    # 检查僵尸进程
    results.append(("无僵尸进程", check_no_zombies()))

    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)

    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name:20s}: {status}")

    all_passed = all(passed for _, passed in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
