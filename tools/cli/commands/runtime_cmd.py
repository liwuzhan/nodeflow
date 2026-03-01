#!/usr/bin/env python3
"""
Runtime Control Command - 运行时控制命令

用于启动、停止、重启和检查 NodeFlow 框架的运行时状态。
支持在后台运行框架，通过 CLI 命令动态控制数据流的启停。
"""

import json
import time
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime


def get_runtime_pid():
    """获取运行时进程的 PID"""
    pid_file = Path("/tmp/nodeflow_runtime.pid")
    if not pid_file.exists():
        return None

    try:
        with open(pid_file, 'r') as f:
            lines = f.readlines()
            if lines:
                return int(lines[0].strip())
    except (ValueError, IOError):
        pass

    return None


def is_runtime_running():
    """检查运行时是否正在运行"""
    pid = get_runtime_pid()
    if pid is None:
        return False

    # 检查进程是否存在
    try:
        os.kill(pid, 0)  # 发送 signal 0 来检查进程是否存在
        return True
    except (OSError, ProcessLookupError):
        return False


def start_runtime(config_path, background=False, log_level="INFO", clean_buffers=True):
    """
    启动运行时框架

    参数：
    - config_path: 配置文件路径
    - background: 是否在后台运行
    - log_level: 日志级别
    - clean_buffers: 是否清理缓冲区
    """
    if is_runtime_running():
        return {
            "status": "already_running",
            "message": "Runtime is already running",
            "pid": get_runtime_pid()
        }

    # 验证配置文件
    if not Path(config_path).exists():
        return {
            "status": "error",
            "message": f"Config file not found: {config_path}"
        }

    # 构建命令
    cmd = [
        sys.executable, "-m", "runtime.main",
        config_path,
        f"--log-level", log_level
    ]

    if not clean_buffers:
        cmd.append("--no-clean-buffers")

    # 在后台模式下，添加 --daemon 参数
    if background:
        cmd.append("--daemon")

    try:
        if background:
            # 在后台启动守护进程
            log_file_path = "/tmp/nodeflow_runtime.log"
            with open(log_file_path, 'w') as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )

            # 等待框架初始化
            time.sleep(2)

            if is_runtime_running():
                return {
                    "status": "success",
                    "message": "Runtime started in background",
                    "pid": get_runtime_pid()
                }
            else:
                return {
                    "status": "error",
                    "message": "Runtime failed to start"
                }
        else:
            # 前台启动
            process = subprocess.Popen(cmd)
            return {
                "status": "success",
                "message": "Runtime started in foreground",
                "pid": process.pid
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to start runtime: {e}"
        }


def _process_alive(pid):
    """检查进程是否存活（即使是 root 进程也能检查）"""
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        # 进程存在但没有权限发信号（root 进程）
        return True
    except ProcessLookupError:
        return False


def _wait_for_exit(pid, timeout_secs):
    """等待进程退出，返回是否已退出"""
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        if not _process_alive(pid):
            return True
        time.sleep(0.5)
    return not _process_alive(pid)


def _reset_pwm_to_center():
    """
    强杀后的安全措施：直接写 sysfs 把所有活跃 PWM 通道设回中位。
    即使进程被 SIGKILL，PWM 硬件仍在输出，必须手动重置。
    """
    pwm_base = Path("/sys/class/pwm")
    if not pwm_base.exists():
        return

    reset_count = 0
    for chip_dir in sorted(pwm_base.iterdir()):
        pwm0_dir = chip_dir / "pwm0"
        if not pwm0_dir.is_dir():
            continue

        enable_path = pwm0_dir / "enable"
        period_path = pwm0_dir / "period"
        duty_path = pwm0_dir / "duty_cycle"

        try:
            if not enable_path.exists():
                continue
            enabled = enable_path.read_text().strip()
            if enabled != "1":
                continue

            period = int(period_path.read_text().strip())
            center_duty = period // 2
            duty_path.write_text(str(center_duty))
            reset_count += 1
        except (OSError, ValueError):
            continue

    return reset_count


def stop_runtime():
    """停止运行时框架（三级策略：共享缓冲区 → sudo kill → sudo kill -9 + PWM 重置）"""
    pid = get_runtime_pid()

    if pid is None:
        return {
            "status": "not_running",
            "message": "Runtime is not running"
        }

    if not _process_alive(pid):
        return {
            "status": "not_running",
            "message": "Runtime process not found (stale PID file)"
        }

    # === 第一级：通过共享缓冲区请求优雅关闭 ===
    try:
        from sdk.shared_buffer_lite import SharedBufferLite
        buf = SharedBufferLite("control.shutdown_request", create=False)
        buf.write({"shutdown": True, "reason": "CLI stop command", "timestamp": time.time()})
    except Exception:
        # 缓冲区不存在（运行时可能未创建），跳过
        pass

    # 等待最多 10 秒让进程优雅退出
    if _wait_for_exit(pid, 10):
        return {
            "status": "success",
            "message": "Runtime stopped gracefully"
        }

    # === 第二级：sudo kill -SIGTERM ===
    try:
        subprocess.run(["sudo", "kill", "-15", str(pid)],
                       capture_output=True, timeout=5)
    except Exception:
        pass

    if _wait_for_exit(pid, 5):
        return {
            "status": "success",
            "message": "Runtime stopped (via sudo SIGTERM)"
        }

    # === 第三级：sudo kill -9 强杀 + PWM 安全重置 ===
    try:
        subprocess.run(["sudo", "kill", "-9", str(pid)],
                       capture_output=True, timeout=5)
    except Exception:
        pass

    time.sleep(0.5)

    # 强杀后 PWM 不会回中位，手动重置
    pwm_reset = _reset_pwm_to_center()

    if not _process_alive(pid):
        msg = "Runtime force-killed"
        if pwm_reset:
            msg += f" (PWM reset to center on {pwm_reset} channel(s))"
        return {
            "status": "success",
            "message": msg
        }

    return {
        "status": "error",
        "message": f"Failed to stop runtime (PID {pid} still alive)"
    }


def get_runtime_status():
    """获取运行时状态"""
    pid = get_runtime_pid()
    running = is_runtime_running()

    result = {
        "status": "running" if running else "not_running",
        "pid": pid
    }

    if running and pid:
        try:
            # 读取进程信息
            with open(f'/proc/{pid}/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS'):
                        memory = line.split()[1]
                        result["memory_mb"] = int(memory) / 1024

            # 读取启动时间
            pid_file = Path("/tmp/nodeflow_runtime.pid")
            if pid_file.exists():
                with open(pid_file, 'r') as f:
                    lines = f.readlines()
                    if len(lines) > 1:
                        start_time = float(lines[1])
                        result["started_at"] = datetime.fromtimestamp(start_time).isoformat()
                        result["uptime_seconds"] = time.time() - start_time
        except:
            pass

    return result


def start_dataflow():
    """启动数据流（通过控制缓冲区）"""
    try:
        from sdk.shared_buffer_lite import SharedBufferLite

        # 写入启动命令到控制缓冲区
        buf = SharedBufferLite("runtime.control", create=True, size=1024)
        buf.write({"command": "start_dataflow", "timestamp": time.time()})

        return {
            "status": "success",
            "message": "Start dataflow command sent"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to send command: {e}"
        }


def stop_dataflow():
    """停止数据流（通过控制缓冲区）"""
    try:
        from sdk.shared_buffer_lite import SharedBufferLite

        # 写入停止命令到控制缓冲区
        buf = SharedBufferLite("runtime.control", create=True, size=1024)
        buf.write({"command": "stop_dataflow", "timestamp": time.time()})

        return {
            "status": "success",
            "message": "Stop dataflow command sent"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to send command: {e}"
        }


def restart_dataflow():
    """重启数据流"""
    result1 = stop_dataflow()
    if result1["status"] != "success":
        return result1

    # 等待停止完成
    time.sleep(1)

    result2 = start_dataflow()
    if result2["status"] != "success":
        return result2

    return {
        "status": "success",
        "message": "Dataflow restarted"
    }


def handle_runtime_command(args):
    """处理运行时命令"""
    subcommand = args.subcommand

    if subcommand == "start":
        result = start_runtime(
            args.config,
            background=args.background,
            log_level=args.log_level,
            clean_buffers=not args.no_clean_buffers
        )

    elif subcommand == "stop":
        result = stop_runtime()

    elif subcommand == "status":
        result = get_runtime_status()

    elif subcommand == "start-dataflow":
        result = start_dataflow()

    elif subcommand == "stop-dataflow":
        result = stop_dataflow()

    elif subcommand == "restart-dataflow":
        result = restart_dataflow()

    else:
        result = {"status": "error", "message": f"Unknown subcommand: {subcommand}"}

    # 输出结果
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("status") == "success":
            print(f"✓ {result.get('message', 'Success')}")
            if "pid" in result:
                print(f"  PID: {result['pid']}")
        elif result.get("status") == "already_running":
            print(f"⚠ {result.get('message', 'Already running')}")
            if "pid" in result:
                print(f"  PID: {result['pid']}")
        elif result.get("status") == "not_running":
            print(f"ℹ {result.get('message', 'Not running')}")
        elif result.get("status") == "running":
            print(f"✓ Runtime is running")
            if "pid" in result:
                print(f"  PID: {result['pid']}")
            if "uptime_seconds" in result:
                hours = result['uptime_seconds'] / 3600
                print(f"  Uptime: {hours:.1f}h")
            if "memory_mb" in result:
                print(f"  Memory: {result['memory_mb']:.1f} MB")
            if "started_at" in result:
                print(f"  Started: {result['started_at']}")
        else:
            print(f"✗ {result.get('message', 'Error')}")

    return 0 if result.get("status") in ["success", "running", "already_running"] else 1
