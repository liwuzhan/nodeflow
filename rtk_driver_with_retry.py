#!/usr/bin/env python3
"""
RTK驱动节点 - 增强版（带自动重连）
自动处理USB连接不稳定的问题
"""

import subprocess
import time
import sys
from datetime import datetime

def log(level, msg):
    """打印日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level:5s}] {msg}")

def run_rtk_system(config_file, timeout=None):
    """运行RTK系统，返回退出码"""
    cmd = [sys.executable, "-m", "runtime.main", config_file]

    try:
        log("INFO", f"启动RTK系统: {' '.join(cmd)}")
        if timeout:
            cmd = ["timeout", str(timeout)] + cmd

        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode
    except Exception as e:
        log("ERROR", f"运行失败: {e}")
        return -1

def main():
    config = "examples/rtk_simple_test.yaml"
    max_retries = 10
    retry_delay = 5  # 秒
    run_duration = 120  # 每次运行120秒

    log("INFO", "RTK驱动系统启动（带自动重连）")
    log("INFO", f"配置: {config}")
    log("INFO", f"最大重试次数: {max_retries}")
    log("INFO", f"重试延迟: {retry_delay}秒")
    log("INFO", f"运行时长: {run_duration}秒")
    log("INFO", "=" * 70)

    for attempt in range(1, max_retries + 1):
        log("INFO", f"")
        log("INFO", f"尝试 {attempt}/{max_retries}")
        log("INFO", "-" * 70)

        exit_code = run_rtk_system(config, timeout=run_duration)

        if exit_code == 0 or exit_code == 124:  # 0=成功，124=timeout
            log("INFO", f"✓ RTK系统运行成功 (退出码: {exit_code})")
            log("INFO", f"✓ 您的RTK驱动节点工作正常！")
            log("INFO", "=" * 70)
            return 0

        if attempt < max_retries:
            log("WARNING", f"系统运行失败 (退出码: {exit_code})")
            log("INFO", f"等待 {retry_delay} 秒后重试...")
            time.sleep(retry_delay)
        else:
            log("ERROR", f"已达到最大重试次数 ({max_retries})")
            log("ERROR", "RTK系统连接不稳定，无法自动恢复")
            log("ERROR", "")
            log("ERROR", "建议解决方案：")
            log("ERROR", "1. 检查USB线缆质量")
            log("ERROR", "2. 尝试不同的USB端口（USB 3.0优先）")
            log("ERROR", "3. 使用带独立供电的USB集线器")
            log("ERROR", "4. 检查RTK设备是否需要外部电源")
            log("ERROR", "5. 改用网络连接（如果设备支持）")
            log("ERROR", "")
            return 1

    return 1

if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        log("INFO", "")
        log("INFO", "用户中断")
        exit(0)
