#!/usr/bin/env python3
"""
Web Teleop Node - Web远程控制节点

提供HTTP Web界面进行速度控制，支持键盘和虚拟手柄输入
"""

import os
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse

from edge.sdk.nodeflow_sdk import NodeFlowSDK


class TeleopHandler(SimpleHTTPRequestHandler):
    """HTTP请求处理器"""

    # 共享状态（由主节点设置）
    node_instance = None

    def __init__(self, *args, **kwargs):
        # 设置静态文件目录
        self.static_dir = Path(__file__).parent / "static"
        super().__init__(*args, directory=str(self.static_dir) if self.static_dir.exists() else None)

    def do_GET(self):
        """处理GET请求"""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            # 主页
            self.serve_index()
        elif parsed.path == "/api/status":
            # 获取当前状态
            self.serve_status()
        elif parsed.path.startswith("/static/"):
            # 静态文件
            super().do_GET()
        else:
            self.send_error(404)

    def do_POST(self):
        """处理POST请求"""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/control":
            self.handle_control()
        elif parsed.path == "/api/stop":
            self.handle_stop()
        elif parsed.path == "/api/mode":
            self.handle_mode()
        else:
            self.send_error(404)

    def serve_index(self):
        """返回主页"""
        index_path = Path(__file__).parent / "static" / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 注入配置
            config = {
                "maxLinearSpeed": self.node_instance.max_linear_speed if self.node_instance else 1.0,
                "maxAngularSpeed": self.node_instance.max_angular_speed if self.node_instance else 1.0,
            }
            content = content.replace("{{CONFIG}}", json.dumps(config))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        else:
            self.send_error(404, "index.html not found")

    def serve_status(self):
        """返回当前状态"""
        if self.node_instance:
            status = self.node_instance.get_status()
            self.send_json(status)
        else:
            self.send_json({"error": "Node not available"})

    def handle_control(self):
        """处理控制命令"""
        try:
            content_length = int(self.headers["Content-Length"])
            data = self.rfile.read(content_length)
            cmd = json.loads(data.decode("utf-8"))

            if self.node_instance:
                self.node_instance.set_velocity(
                    cmd.get("linear", 0.0),
                    cmd.get("angular", 0.0)
                )

            self.send_json({"status": "ok"})
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def handle_stop(self):
        """处理停止命令"""
        if self.node_instance:
            self.node_instance.set_velocity(0.0, 0.0)
        self.send_json({"status": "stopped"})

    def handle_mode(self):
        """处理模式切换命令"""
        try:
            content_length = int(self.headers["Content-Length"])
            data = self.rfile.read(content_length)
            cmd = json.loads(data.decode("utf-8"))

            if self.node_instance:
                enabled = cmd.get("passthrough", False)
                self.node_instance.set_passthrough(enabled)
                self.send_json({"status": "ok", "passthrough_enabled": enabled})
            else:
                self.send_json({"error": "Node not available"}, 503)
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def send_json(self, data, status_code=200):
        """发送JSON响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        """禁用默认日志"""
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """支持多线程的HTTP服务器"""
    daemon = True


class WebTeleopNode:
    """Web远程控制节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.running = True

        # ========== 读取参数 ==========
        self.http_host = sdk.get_param('http_host', '0.0.0.0')
        self.http_port = int(sdk.get_param('http_port', 9873))
        self.max_linear_speed = float(sdk.get_param('max_linear_speed', 1.0))
        self.max_angular_speed = float(sdk.get_param('max_angular_speed', 1.0))
        self.continuous_output = sdk.get_param('continuous_output', True)
        self.output_rate = float(sdk.get_param('output_rate', 10.0))
        self.require_stop_on_disconnect = sdk.get_param('require_stop_on_disconnect', False)
        self.command_timeout = float(sdk.get_param('command_timeout', 5.0))
        self.passthrough_mode = sdk.get_param('passthrough_mode', False)

        # ========== 创建端口 ==========
        self.velocity_cmd_port = sdk.create_output_port('velocity_cmd')

        # feedback 端口是可选的，只有配置了才创建
        if os.getenv('NODE_IN_feedback'):
            self.feedback_port = sdk.create_input_port('feedback')
        else:
            self.feedback_port = None

        # auto_velocity 端口是可选的（透传模式下使用）
        if os.getenv('NODE_IN_auto_velocity'):
            self.auto_velocity_port = sdk.create_input_port('auto_velocity')
        else:
            self.auto_velocity_port = None

        # ========== 状态 ==========
        self.current_linear = 0.0
        self.current_angular = 0.0
        self.feedback_linear = 0.0
        self.feedback_angular = 0.0
        self.last_command_time = time.time()
        self.connected_clients = 0
        self.passthrough_enabled = self.passthrough_mode  # 是否启用透传（可动态切换）

        # 启动HTTP服务器
        self.http_server = None
        self.server_thread = None
        self._start_http_server()

        # 日志
        self.sdk.logger.info(f"Web Teleop started on http://{self.http_host}:{self.http_port}")
        self.sdk.logger.info(f"  Max linear speed: {self.max_linear_speed} m/s")
        self.sdk.logger.info(f"  Max angular speed: {self.max_angular_speed} rad/s")
        self.sdk.logger.info(f"  Passthrough mode: {self.passthrough_mode}")

    def _start_http_server(self):
        """启动HTTP服务器"""
        # 设置处理器引用
        TeleopHandler.node_instance = self

        try:
            self.http_server = ThreadedHTTPServer(
                (self.http_host, self.http_port),
                TeleopHandler
            )
            self.server_thread = threading.Thread(
                target=self.http_server.serve_forever,
                daemon=True
            )
            self.server_thread.start()
            self.sdk.logger.info(f"HTTP server listening on :{self.http_port}")
        except Exception as e:
            self.sdk.logger.error(f"Failed to start HTTP server: {e}")

    def set_velocity(self, linear: float, angular: float):
        """设置速度（透传模式下忽略）"""
        if self.passthrough_enabled:
            return  # 透传模式下忽略手动控制

        # 限制范围
        self.current_linear = max(-self.max_linear_speed, min(self.max_linear_speed, linear))
        self.current_angular = max(-self.max_angular_speed, min(self.max_angular_speed, angular))
        self.last_command_time = time.time()

        # 立即发送命令
        self._send_velocity_command()

    def set_passthrough(self, enabled: bool):
        """设置透传模式"""
        self.passthrough_enabled = enabled
        self.sdk.logger.info(f"Passthrough mode: {'enabled' if enabled else 'disabled'}")

        # 切换到手动模式时，先停止
        if not enabled:
            self.current_linear = 0.0
            self.current_angular = 0.0
            self._send_velocity_command()

    def _send_velocity_command(self):
        """发送速度命令"""
        cmd = {
            "linear_velocity": self.current_linear,
            "angular_velocity": self.current_angular,
            "timestamp": time.time()
        }
        self.velocity_cmd_port.send(cmd)

    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            "command": {
                "linear_velocity": round(self.current_linear, 3),
                "angular_velocity": round(self.current_angular, 3),
            },
            "feedback": {
                "linear_velocity": round(self.feedback_linear, 3),
                "angular_velocity": round(self.feedback_angular, 3),
            },
            "limits": {
                "max_linear_speed": self.max_linear_speed,
                "max_angular_speed": self.max_angular_speed,
            },
            "connected_clients": self.connected_clients,
            "uptime": time.time() - self.last_command_time if self.last_command_time > 0 else 0,
            "passthrough_enabled": self.passthrough_enabled,
        }

    def run(self):
        """主循环"""
        self.sdk.logger.info("Web Teleop node running")
        last_output_time = time.time()
        output_interval = 1.0 / self.output_rate if self.output_rate > 0 else 0.1

        try:
            while self.running:
                current_time = time.time()

                # 读取反馈
                if self.feedback_port:
                    feedback = self.feedback_port.recv_latest()
                    if feedback:
                        self.feedback_linear = feedback.get("linear_velocity", 0.0)
                        self.feedback_angular = feedback.get("angular_velocity", 0.0)

                # 透传模式：转发自动控制的速度命令
                if self.passthrough_enabled and self.auto_velocity_port:
                    auto_cmd = self.auto_velocity_port.recv_latest()
                    if auto_cmd:
                        self.current_linear = auto_cmd.get("linear_velocity", 0.0)
                        self.current_angular = auto_cmd.get("angular_velocity", 0.0)
                        self._send_velocity_command()
                else:
                    # 手动模式
                    # 检查超时
                    time_since_command = current_time - self.last_command_time
                    if time_since_command > self.command_timeout and (self.current_linear != 0 or self.current_angular != 0):
                        self.current_linear = 0.0
                        self.current_angular = 0.0
                        self.sdk.logger.info("Command timeout, stopping")

                    # 持续输出模式
                    if self.continuous_output:
                        if current_time - last_output_time >= output_interval:
                            self._send_velocity_command()
                            last_output_time = current_time

                time.sleep(0.05)  # 20Hz 检查频率

        except KeyboardInterrupt:
            self.sdk.logger.info("Web Teleop shutting down (Ctrl+C)")
        except Exception as e:
            self.sdk.logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            self.running = False
            self.cleanup()

    def cleanup(self):
        """清理资源"""
        # 停止
        self.current_linear = 0.0
        self.current_angular = 0.0
        self._send_velocity_command()

        # 关闭HTTP服务器
        if self.http_server:
            self.http_server.shutdown()
            self.sdk.logger.info("HTTP server stopped")


def main():
    """节点主入口"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        node = WebTeleopNode(sdk)
        node.run()


if __name__ == '__main__':
    main()
