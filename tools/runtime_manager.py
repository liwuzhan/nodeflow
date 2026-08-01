#!/usr/bin/env python3.12
"""
Runtime Manager - NodeFlow 运行时进程管理
提供 PID 文件管理、进程状态监控、日志访问等功能
"""

import os
import signal
import time
import psutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import subprocess


@dataclass
class RuntimeStatus:
    """运行时状态信息"""

    is_running: bool
    pid: Optional[int]
    start_time: Optional[float]
    uptime_seconds: Optional[float]
    node_count: int
    active_nodes: List[Dict[str, Any]]
    log_dir: str


@dataclass
class NodeStatus:
    """节点状态信息"""

    node_id: str
    pid: int
    is_alive: bool
    status: str
    cpu_percent: float
    memory_mb: float
    runtime_seconds: float


class PidManager:
    """PID 文件管理器"""

    PID_FILE = "/tmp/nodeflow_runtime.pid"

    @classmethod
    def write_pid(cls, pid: int) -> None:
        """
        写入 PID 文件

        Args:
            pid: 进程 ID
        """
        try:
            with open(cls.PID_FILE, "w") as f:
                f.write(f"{pid}\n{time.time()}")
        except Exception as e:
            raise RuntimeError(f"Failed to write PID file: {e}")

    @classmethod
    def read_pid(cls) -> Optional[Tuple[int, float]]:
        """
        读取 PID 文件

        Returns:
            (pid, start_time) 元组，如果文件不存在或格式错误返回 None
        """
        try:
            with open(cls.PID_FILE, "r") as f:
                lines = f.readlines()
                if len(lines) >= 2:
                    pid = int(lines[0].strip())
                    start_time = float(lines[1].strip())
                    return pid, start_time
                return None
        except (FileNotFoundError, ValueError, IndexError):
            return None

    @classmethod
    def clear_pid(cls) -> None:
        """清理 PID 文件"""
        try:
            pid_file = Path(cls.PID_FILE)
            if pid_file.exists():
                pid_file.unlink()
        except Exception as e:
            # 记录警告但不抛出异常，避免影响主流程
            print(f"Warning: Failed to clear PID file: {e}")


class RuntimeManager:
    """运行时进程管理器"""

    from edge.runtime.utils.constants import LOGS_DIR as LOG_DIR

    def __init__(self):
        self.log_dir = Path(self.LOG_DIR)
        self.log_dir.mkdir(exist_ok=True)

    def get_runtime_status(self) -> RuntimeStatus:
        """
        获取运行时状态

        Returns:
            RuntimeStatus 对象
        """
        pid_info = PidManager.read_pid()

        if not pid_info:
            return RuntimeStatus(
                is_running=False,
                pid=None,
                start_time=None,
                uptime_seconds=None,
                node_count=0,
                active_nodes=[],
                log_dir=self.LOG_DIR,
            )

        pid, start_time = pid_info

        # 检查主进程是否存在
        try:
            main_process = psutil.Process(pid)
            if not main_process.is_running():
                # 进程不存在，清理 PID 文件
                PidManager.clear_pid()
                return self._get_stopped_status()

            # 获取子进程（节点进程）
            node_processes = []
            try:
                for child in main_process.children(recursive=True):
                    try:
                        with child.oneshot():
                            node_info = {
                                "pid": child.pid,
                                "name": child.name(),
                                "status": child.status(),
                                "cpu_percent": child.cpu_percent(),
                                "memory_mb": child.memory_info().rss / 1024 / 1024,
                                "runtime_seconds": time.time() - child.create_time(),
                            }
                            node_processes.append(node_info)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # 进程可能在检查期间退出
                        continue
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # 主进程可能在检查期间退出
                PidManager.clear_pid()
                return self._get_stopped_status()

            return RuntimeStatus(
                is_running=True,
                pid=pid,
                start_time=start_time,
                uptime_seconds=time.time() - start_time,
                node_count=len(node_processes),
                active_nodes=node_processes,
                log_dir=self.LOG_DIR,
            )

        except psutil.NoSuchProcess:
            # 主进程不存在，清理 PID 文件
            PidManager.clear_pid()
            return self._get_stopped_status()

    def _get_stopped_status(self) -> RuntimeStatus:
        """获取已停止状态的 RuntimeStatus"""
        return RuntimeStatus(
            is_running=False,
            pid=None,
            start_time=None,
            uptime_seconds=None,
            node_count=0,
            active_nodes=[],
            log_dir=self.LOG_DIR,
        )

    def start_runtime(
        self, yaml_path: str, duration: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        启动运行时

        Args:
            yaml_path: YAML 配置文件路径
            duration: 可选的运行时长（秒）

        Returns:
            启动结果字典
        """
        # 检查是否已运行
        status = self.get_runtime_status()
        if status.is_running:
            return {
                "success": False,
                "error": "Runtime already running",
                "pid": status.pid,
                "uptime": status.uptime_seconds,
            }

        # 检查 YAML 文件是否存在
        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            return {"success": False, "error": f"YAML file not found: {yaml_path}"}

        # 构建启动命令
        cmd = [
            "python3",
            "-m",
            "edge.runtime.main",
            str(yaml_file.absolute()),
            "--log-level",
            "INFO",
        ]

        if duration is not None:
            cmd.extend(["--duration", str(duration)])

        try:
            # 创建日志目录
            log_dir = Path(self.LOG_DIR)
            log_dir.mkdir(parents=True, exist_ok=True)

            # 打开日志文件（不使用 PIPE 以避免缓冲区阻塞）
            stdout_log = log_dir / "runtime.stdout.log"
            stderr_log = log_dir / "runtime.stderr.log"

            with open(stdout_log, "a") as stdout_f, open(stderr_log, "a") as stderr_f:
                # 启动运行时进程，重定向到日志文件
                process = subprocess.Popen(
                    cmd, stdout=stdout_f, stderr=stderr_f, text=True, cwd=Path.cwd()
                )

            # 等待启动完成（最多 30 秒）
            startup_timeout = 30
            for i in range(startup_timeout):
                if process.poll() is not None:
                    # 进程已退出
                    return {
                        "success": False,
                        "error": "Runtime startup failed",
                        "exit_code": process.returncode,
                        "log_file": str(stdout_log),
                    }

                # 检查 PID 文件是否生成（改进的启动成功判定）
                pid_info = PidManager.read_pid()
                if pid_info and pid_info[0] == process.pid:
                    # PID 文件生成成功，表示运行时已初始化
                    return {
                        "success": True,
                        "message": "Runtime started successfully",
                        "pid": process.pid,
                        "duration": duration,
                        "log_dir": self.LOG_DIR,
                    }

                time.sleep(1)

            # 启动超时
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

            return {
                "success": False,
                "error": "Runtime startup timeout",
                "pid": process.pid,
                "log_file": str(stdout_log),
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to start runtime: {str(e)}"}

    def stop_runtime(self, timeout: int = 10) -> Dict[str, Any]:
        """
        停止运行时

        Args:
            timeout: 等待退出的超时时间（秒）

        Returns:
            停止结果字典
        """
        pid_info = PidManager.read_pid()
        if not pid_info:
            return {"success": False, "error": "Runtime not running"}

        pid, start_time = pid_info

        try:
            process = psutil.Process(pid)

            # 发送 SIGTERM 信号
            process.terminate()

            # 等待进程退出
            try:
                process.wait(timeout=timeout)
                result = {
                    "success": True,
                    "message": "Runtime stopped gracefully",
                    "pid": pid,
                    "runtime_seconds": time.time() - start_time,
                }
            except psutil.TimeoutExpired:
                # 强制杀死进程
                process.kill()
                result = {
                    "success": True,
                    "message": "Runtime stopped forcefully",
                    "pid": pid,
                    "runtime_seconds": time.time() - start_time,
                }

            # 清理 PID 文件
            PidManager.clear_pid()

            return result

        except psutil.NoSuchProcess:
            # 进程不存在，清理 PID 文件
            PidManager.clear_pid()
            return {"success": True, "message": "Runtime already stopped", "pid": pid}
        except Exception as e:
            return {"success": False, "error": f"Failed to stop runtime: {str(e)}"}

    def read_logs(
        self,
        node_id: str,
        stream: str = "both",
        tail: Optional[int] = None,
        max_lines: int = 1000,
        max_size: int = 1024 * 1024,
    ) -> Dict[str, Any]:
        """
        读取节点日志

        Args:
            node_id: 节点 ID
            stream: 日志流类型 ("stdout", "stderr", "both")
            tail: 可选，读取最后 N 行
            max_lines: 最大读取行数
            max_size: 最大读取字节数

        Returns:
            日志内容字典
        """
        # 验证 node_id 安全性 - 防止路径穿越
        if not node_id or "/" in node_id or "\\" in node_id or ".." in node_id:
            return {
                "success": False,
                "error": f'Invalid node_id: cannot contain path separators or ".." (got: {node_id})',
            }

        result: Dict[str, Any] = {"success": True, "node_id": node_id, "logs": {}}

        streams_to_read = []
        if stream == "stdout":
            streams_to_read = ["stdout"]
        elif stream == "stderr":
            streams_to_read = ["stderr"]
        elif stream == "both":
            streams_to_read = ["stdout", "stderr"]
        else:
            return {
                "success": False,
                "error": f"Invalid stream: {stream}. Must be stdout, stderr, or both",
            }

        for stream_type in streams_to_read:
            log_file = self.log_dir / f"{node_id}.{stream_type}.log"

            if not log_file.exists():
                result["logs"][stream_type] = []
                continue

            try:
                # 检查文件大小
                if log_file.stat().st_size > max_size:
                    result["logs"][stream_type] = [
                        f"Log file too large (> {max_size} bytes)"
                    ]
                    continue

                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                # 应用 tail 选项
                if tail is not None and tail > 0:
                    lines = lines[-tail:]

                # 限制行数
                if len(lines) > max_lines:
                    lines = lines[-max_lines:]

                # 清理换行符
                result["logs"][stream_type] = [line.rstrip("\n\r") for line in lines]

            except Exception as e:
                result["logs"][stream_type] = [f"Error reading log: {str(e)}"]

        return result

    def list_available_logs(self) -> List[str]:
        """
        列出所有可用的日志文件

        Returns:
            节点 ID 列表
        """
        node_ids = set()

        try:
            for log_file in self.log_dir.glob("*.log"):
                # 文件名格式: <node_id>.<stream>.log
                parts = log_file.stem.split(".")
                if len(parts) >= 2:
                    node_ids.add(parts[0])
        except Exception:
            pass

        return sorted(list(node_ids))

    def get_node_details(self, node_id: str) -> Optional[NodeStatus]:
        """
        获取特定节点的详细状态

        Args:
            node_id: 节点 ID

        Returns:
            NodeStatus 对象，如果节点不存在返回 None
        """
        runtime_status = self.get_runtime_status()

        if not runtime_status.is_running:
            return None

        # 查找匹配的���点进程
        for node_info in runtime_status.active_nodes:
            if node_id in node_info.get("name", ""):
                return NodeStatus(
                    node_id=node_id,
                    pid=node_info["pid"],
                    is_alive=node_info["status"] == psutil.STATUS_RUNNING,
                    status=node_info["status"],
                    cpu_percent=node_info["cpu_percent"],
                    memory_mb=node_info["memory_mb"],
                    runtime_seconds=node_info["runtime_seconds"],
                )

        return None
