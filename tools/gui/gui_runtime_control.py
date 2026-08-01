#!/usr/bin/env python3
"""
NodeFlow Runtime Control GUI

简单的图形界面，用于管理 NodeFlow 数据流：
- 选择配置文件
- 启动/停止 Runtime
- 启动/停止数据流
- 查看运行状态
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import sys
import os
import subprocess
import threading
import time
from pathlib import Path

# 添加项目根目录到路径 (gui/ 的父目录)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class NodeFlowGUI:
    """NodeFlow Runtime 控制面板"""

    def __init__(self, root):
        self.root = root
        self.root.title("NodeFlow Runtime Control Panel")
        self.root.geometry("900x700")

        # 配置文件目录
        self.examples_dir = project_root / "examples"

        # 状态更新线程
        self.status_update_thread = None
        self.running = True

        # Runtime 进程
        self.runtime_process = None
        self.pid_file = Path("/tmp/nodeflow_runtime.pid")

        # 创建界面
        self.create_widgets()

        # 启动状态监控
        self.start_status_monitoring()

        # 窗口关闭时的处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.log("GUI 启动完成，请选择配置文件后点击启动按钮")

    def create_widgets(self):
        """创建界面组件"""

        # ========== 顶部：配置文件选择 ==========
        config_frame = ttk.LabelFrame(self.root, text="配置文件选择", padding=10)
        config_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(config_frame, text="数据流配置:").pack(side="left", padx=5)

        # 获取所有 yaml 文件
        yaml_files = sorted([f.name for f in self.examples_dir.glob("*.yaml")])

        self.config_var = tk.StringVar()
        self.config_combo = ttk.Combobox(
            config_frame,
            textvariable=self.config_var,
            values=yaml_files,
            width=50,
            state="readonly"
        )
        self.config_combo.pack(side="left", padx=5)

        # 默认选择 planning_simulation.yaml
        if yaml_files:
            try:
                idx = yaml_files.index("planning_simulation.yaml")
                self.config_combo.current(idx)
            except ValueError:
                self.config_combo.current(0)

        # 刷新按钮
        ttk.Button(config_frame, text="刷新", command=self.refresh_configs).pack(side="left", padx=5)

        # ========== 中部：控制按钮 ==========
        control_frame = ttk.LabelFrame(self.root, text="控制面板", padding=10)
        control_frame.pack(fill="x", padx=10, pady=5)

        # Runtime 控制
        runtime_frame = ttk.Frame(control_frame)
        runtime_frame.pack(fill="x", pady=5)

        ttk.Label(runtime_frame, text="Runtime:", font=("", 10, "bold")).pack(side="left", padx=5)

        self.btn_start_runtime = ttk.Button(
            runtime_frame,
            text="▶ 启动 Runtime",
            command=self.start_runtime,
            width=18
        )
        self.btn_start_runtime.pack(side="left", padx=5)

        self.btn_stop_runtime = ttk.Button(
            runtime_frame,
            text="⏹ 停止 Runtime",
            command=self.stop_runtime,
            width=18,
            state="disabled"
        )
        self.btn_stop_runtime.pack(side="left", padx=5)

        # 数据流控制
        dataflow_frame = ttk.Frame(control_frame)
        dataflow_frame.pack(fill="x", pady=5)

        ttk.Label(dataflow_frame, text="数据流:", font=("", 10, "bold")).pack(side="left", padx=5)

        self.btn_start_dataflow = ttk.Button(
            dataflow_frame,
            text="▶ 启动数据流",
            command=self.start_dataflow,
            width=18,
            state="disabled"
        )
        self.btn_start_dataflow.pack(side="left", padx=5)

        self.btn_stop_dataflow = ttk.Button(
            dataflow_frame,
            text="⏹ 停止数据流",
            command=self.stop_dataflow,
            width=18,
            state="disabled"
        )
        self.btn_stop_dataflow.pack(side="left", padx=5)

        self.btn_restart_dataflow = ttk.Button(
            dataflow_frame,
            text="🔄 重启数据流",
            command=self.restart_dataflow,
            width=18,
            state="disabled"
        )
        self.btn_restart_dataflow.pack(side="left", padx=5)

        # ========== 状态显示 ==========
        status_frame = ttk.LabelFrame(self.root, text="运行状态", padding=10)
        status_frame.pack(fill="x", padx=10, pady=5)

        self.status_text = tk.StringVar()
        self.status_text.set("● Runtime: 未运行 | 数据流: 未运行")

        status_label = ttk.Label(
            status_frame,
            textvariable=self.status_text,
            font=("Courier", 11)
        )
        status_label.pack()

        # ========== 日志输出 ==========
        log_frame = ttk.LabelFrame(self.root, text="日志输出", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            width=100,
            height=20,
            font=("Courier", 9)
        )
        self.log_text.pack(fill="both", expand=True)

        # 配置日志标签颜色
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("warning", foreground="orange")

        # 清除日志按钮
        btn_frame = ttk.Frame(log_frame)
        btn_frame.pack(pady=5)

        ttk.Button(btn_frame, text="清除日志", command=self.clear_log).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="查看 Runtime 日志", command=self.view_runtime_log).pack(side="left", padx=5)

    def refresh_configs(self):
        """刷新配置文件列表"""
        yaml_files = sorted([f.name for f in self.examples_dir.glob("*.yaml")])
        self.config_combo['values'] = yaml_files
        self.log("已刷新配置文件列表")

    def log(self, message, tag=None):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)

    def clear_log(self):
        """清除日志"""
        self.log_text.delete(1.0, tk.END)

    def view_runtime_log(self):
        """查看 Runtime 日志文件"""
        log_file = Path("/tmp/nodeflow_runtime.log")
        if log_file.exists():
            self.log("--- Runtime 日志 (最后 30 行) ---", "warning")
            try:
                with open(log_file, "r") as f:
                    lines = f.readlines()
                    for line in lines[-30:]:
                        line = line.strip()
                        if "ERROR" in line:
                            self.log(line, "error")
                        elif "WARNING" in line:
                            self.log(line, "warning")
                        else:
                            self.log(line)
            except Exception as e:
                self.log(f"读取日志失败: {e}", "error")
            self.log("--- 日志结束 ---", "warning")
        else:
            self.log("Runtime 日志文件不存在", "warning")

    def get_selected_config_path(self):
        """获取选中的配置文件路径"""
        config_name = self.config_var.get()
        if not config_name:
            messagebox.showerror("错误", "请先选择配置文件")
            return None
        return str(self.examples_dir / config_name)

    def check_runtime_status(self):
        """检查 Runtime 状态"""
        if self.pid_file.exists():
            try:
                # PID 文件可能包含多行（PID + 时间戳），只读取第一行
                content = self.pid_file.read_text().strip()
                first_line = content.split('\n')[0].strip()
                pid = int(first_line)
                # 检查进程是否存在
                os.kill(pid, 0)
                return True, pid
            except (ValueError, ProcessLookupError, PermissionError, IndexError):
                return False, None
        return False, None

    def start_runtime(self):
        """启动 Runtime (使用 CLI 命令)"""
        config_path = self.get_selected_config_path()
        if not config_path:
            return

        config_name = Path(config_path).name
        self.log(f"启动 Runtime: {config_name}...", "warning")

        # 禁用按钮防止重复点击
        self.btn_start_runtime.config(state="disabled")

        def task():
            try:
                # 使用 CLI 命令启动
                cmd = [
                    sys.executable, "-m", "tools.cli.core.cli",
                    "runtime", "start", config_path, "--background"
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=30
                )

                # 在主线程中更新 UI
                self.root.after(0, self._handle_start_result, result)

            except subprocess.TimeoutExpired:
                self.root.after(0, self.log, "启动超时 (30秒)", "error")
                self.root.after(0, self.btn_start_runtime.config, {"state": "normal"})
            except Exception as e:
                self.root.after(0, self.log, f"启动异常: {e}", "error")
                self.root.after(0, self.btn_start_runtime.config, {"state": "normal"})

        threading.Thread(target=task, daemon=True).start()

    def _handle_start_result(self, result):
        """处理启动结果"""
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            self.log(stdout)
        if stderr:
            self.log(stderr, "error")

        if result.returncode == 0:
            self.log("✓ Runtime 启动成功", "success")
            self.update_button_states(runtime_running=True)
        else:
            self.log(f"✗ Runtime 启动失败 (exit code: {result.returncode})", "error")
            self.btn_start_runtime.config(state="normal")

    def stop_runtime(self):
        """停止 Runtime"""
        self.log("停止 Runtime...", "warning")
        self.btn_stop_runtime.config(state="disabled")

        def task():
            try:
                cmd = [
                    sys.executable, "-m", "tools.cli.core.cli",
                    "runtime", "stop"
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=30
                )

                self.root.after(0, self._handle_stop_result, result)

            except Exception as e:
                self.root.after(0, self.log, f"停止异常: {e}", "error")

        threading.Thread(target=task, daemon=True).start()

    def _handle_stop_result(self, result):
        """处理停止结果"""
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            self.log(stdout)
        if stderr and "not_running" not in stderr:
            self.log(stderr, "error")

        self.log("✓ Runtime 已停止", "success")
        self.update_button_states(runtime_running=False)

    def start_dataflow(self):
        """启动数据流"""
        self.log("启动数据流...", "warning")

        def task():
            try:
                cmd = [
                    sys.executable, "-m", "tools.cli.core.cli",
                    "runtime", "start-dataflow"
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=60
                )

                self.root.after(0, self._handle_dataflow_result, result, "启动")

            except Exception as e:
                self.root.after(0, self.log, f"启动数据流异常: {e}", "error")

        threading.Thread(target=task, daemon=True).start()

    def stop_dataflow(self):
        """停止数据流"""
        self.log("停止数据流...", "warning")

        def task():
            try:
                cmd = [
                    sys.executable, "-m", "tools.cli.core.cli",
                    "runtime", "stop-dataflow"
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=30
                )

                self.root.after(0, self._handle_dataflow_result, result, "停止")

            except Exception as e:
                self.root.after(0, self.log, f"停止数据流异常: {e}", "error")

        threading.Thread(target=task, daemon=True).start()

    def restart_dataflow(self):
        """重启数据流"""
        self.log("重启数据流...", "warning")

        def task():
            try:
                cmd = [
                    sys.executable, "-m", "tools.cli.core.cli",
                    "runtime", "restart-dataflow"
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=60
                )

                self.root.after(0, self._handle_dataflow_result, result, "重启")

            except Exception as e:
                self.root.after(0, self.log, f"重启数据流异常: {e}", "error")

        threading.Thread(target=task, daemon=True).start()

    def _handle_dataflow_result(self, result, action):
        """处理数据流操作结果"""
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            self.log(stdout)
        if stderr:
            self.log(stderr, "error")

        if result.returncode == 0:
            self.log(f"✓ 数据流{action}成功", "success")
        else:
            self.log(f"✗ 数据流{action}失败", "error")

    def update_button_states(self, runtime_running=None):
        """更新按钮状态"""
        if runtime_running is not None:
            if runtime_running:
                # Runtime 运行中
                self.btn_start_runtime.config(state="disabled")
                self.btn_stop_runtime.config(state="normal")
                self.btn_start_dataflow.config(state="normal")
                self.btn_stop_dataflow.config(state="normal")
                self.btn_restart_dataflow.config(state="normal")
            else:
                # Runtime 未运行
                self.btn_start_runtime.config(state="normal")
                self.btn_stop_runtime.config(state="disabled")
                self.btn_start_dataflow.config(state="disabled")
                self.btn_stop_dataflow.config(state="disabled")
                self.btn_restart_dataflow.config(state="disabled")

    def start_status_monitoring(self):
        """启动状态监控"""
        def monitor():
            last_status = None
            start_time = None

            while self.running:
                try:
                    # 检查 Runtime 状态
                    running, pid = self.check_runtime_status()

                    if running:
                        # 计算运行时间
                        if last_status != "running":
                            start_time = time.time()
                        last_status = "running"

                        if start_time:
                            uptime = time.time() - start_time
                            if uptime < 60:
                                uptime_str = f"{uptime:.0f}s"
                            elif uptime < 3600:
                                uptime_str = f"{uptime/60:.1f}m"
                            else:
                                uptime_str = f"{uptime/3600:.1f}h"
                        else:
                            uptime_str = "N/A"

                        status_msg = f"● Runtime: 运行中 (PID: {pid}, 运行时间: {uptime_str})"
                        runtime_running = True
                    else:
                        last_status = "stopped"
                        start_time = None
                        status_msg = "○ Runtime: 未运行"
                        runtime_running = False

                    # 在主线程中更新 UI
                    self.root.after(0, self.status_text.set, status_msg)
                    self.root.after(0, self.update_button_states, runtime_running)

                except Exception as e:
                    pass

                # 每 2 秒更新一次
                time.sleep(2)

        self.status_update_thread = threading.Thread(target=monitor, daemon=True)
        self.status_update_thread.start()

    def on_closing(self):
        """窗口关闭时的处理"""
        self.running = False
        self.root.destroy()


def main():
    """主函数"""
    root = tk.Tk()

    # 设置样式
    style = ttk.Style()
    style.theme_use('default')

    # 创建 GUI
    app = NodeFlowGUI(root)

    # 启动主循环
    root.mainloop()


if __name__ == '__main__':
    main()
