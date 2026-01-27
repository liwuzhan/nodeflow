#!/usr/bin/env python3
"""
Logger Node - 多输入日志记录节点 (L3 分子层)

L3 职责：只负责数据搬运和调用 L4 原子层
- 从输入端口读取数据
- 调用 atom.py 处理日志条目
- 管理 Web 服务器和文件输出
- 保证线程安全

架构：
- atom.py (L4): 纯算法，无依赖
- run.py (L3): 数据搬运 + Web 服务
"""

import asyncio
import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from threading import Thread, Lock

# 添加项目根路径到 sys.path（使 sdk.* 包导入正常工作）
project_root = os.path.join(os.path.dirname(__file__), '../../..')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# FastAPI 导入（L3 依赖）
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

from sdk.nodeflow_sdk import NodeFlowSDK

# 导入 L4 原子层
import atom


class ThreadSafeLogBuffer:
    """线程安全的日志缓冲区包装器"""

    def __init__(self, max_size: int = 1000):
        self.buffer = atom.LogBuffer(max_size)
        self.lock = Lock()
        self.subscribers: List[WebSocket] = []

    def add_entry(self, entry: Dict[str, Any]) -> atom.LogEntry:
        """添加日志条目（线程安全）"""
        with self.lock:
            log_entry = self.buffer.add_entry(entry)
            return log_entry

    def get_all(self) -> List[atom.LogEntry]:
        """获取所有日志条目（线程安全）"""
        with self.lock:
            return self.buffer.get_all()

    def get_recent(self, count: int) -> List[atom.LogEntry]:
        """获取最近的 N 条日志（线程安全）"""
        with self.lock:
            return self.buffer.get_recent(count)

    def clear(self) -> None:
        """清空缓冲区（线程安全）"""
        with self.lock:
            self.buffer.clear()

    def size(self) -> int:
        """当前缓冲区大小（线程安全）"""
        with self.lock:
            return self.buffer.size()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓冲区统计信息（线程安全）"""
        with self.lock:
            return self.buffer.get_stats()

    def add_subscriber(self, websocket: WebSocket) -> None:
        """添加 WebSocket 订阅者"""
        self.subscribers.append(websocket)

    def remove_subscriber(self, websocket: WebSocket) -> None:
        """移除 WebSocket 订阅者"""
        if websocket in self.subscribers:
            self.subscribers.remove(websocket)

    def get_subscriber_count(self) -> int:
        """获取订阅者数量"""
        return len(self.subscribers)


class LoggerNode:
    """日志记录节点 (L3)"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.running = True

        # 参数配置
        self.web_port = int(sdk.get_param('web_port', 8001))
        self.buffer_size = int(sdk.get_param('buffer_size', 1000))
        self.enable_file_log = sdk.get_param('enable_file_log', False) in [True, 'true', 'True']
        self.log_file_path = sdk.get_param('log_file_path', './logs/logger.jsonl')

        # 创建输入端口
        self.input_ports = {
            'input1': sdk.create_input_port('input1'),
            'input2': sdk.create_input_port('input2'),
            'input3': sdk.create_input_port('input3'),
        }

        # 初始化线程安全缓冲区
        self.log_buffer = ThreadSafeLogBuffer(self.buffer_size)

        # 文件日志
        self.log_file: Optional[Any] = None
        if self.enable_file_log:
            self._setup_file_logging()

        # FastAPI 应用
        self.sdk.logger.info("Creating FastAPI app")
        self.app = FastAPI(title="NodeFlow Logger")
        self.sdk.logger.info("Setting up routes")
        self._setup_routes()
        self.sdk.logger.info("Routes setup complete")

        # Web 服务线程
        self.web_thread: Optional[Thread] = None
        self.sdk.logger.info("LoggerNode __init__ complete")

    def _setup_file_logging(self) -> None:
        """初始化文件日志"""
        try:
            log_path = Path(self.log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
            self.sdk.logger.info(f"File logging enabled: {self.log_file_path}")
        except Exception as e:
            self.sdk.logger.error(f"Failed to setup file logging: {e}")

    def _setup_routes(self) -> None:
        """设置 FastAPI 路由"""

        @self.app.get("/", response_class=HTMLResponse)
        async def get_dashboard():
            """返回主仪表盘页面"""
            return self._get_html_template()

        @self.app.get("/api/logs")
        async def get_logs():
            """获取历史日志"""
            logs = self.log_buffer.get_all()
            # 转换为字典格式（兼容现有 Web 界面）
            logs_dict = [entry.to_dict() if hasattr(entry, 'to_dict') else entry
                        for entry in logs]
            return {
                "count": len(logs_dict),
                "logs": logs_dict,
                "buffer_size": self.buffer_size,
                "subscribers": self.log_buffer.get_subscriber_count()
            }

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 连接处理"""
            await websocket.accept()
            self.log_buffer.add_subscriber(websocket)
            self.sdk.logger.debug("WebSocket subscriber connected")

            try:
                while True:
                    # 保持连接开放
                    data = await websocket.receive_text()
            except WebSocketDisconnect:
                self.log_buffer.remove_subscriber(websocket)
                self.sdk.logger.debug("WebSocket subscriber disconnected")
            except Exception as e:
                self.sdk.logger.error(f"WebSocket error: {e}")
                self.log_buffer.remove_subscriber(websocket)

    def _get_html_template(self) -> str:
        """生成内嵌的 HTML 仪表盘"""
        # 使用现有 HTML 模板（保持不变）
        html_template_path = Path(__file__).parent / "web_template.html"
        if html_template_path.exists():
            with open(html_template_path, 'r', encoding='utf-8') as f:
                return f.read()

        # 如果模板文件不存在，使用内嵌模板（现有代码中的模板）
        # 这里为了简洁，我们保留现有内嵌模板
        # 实际项目中可以将 HTML 提取到单独文件
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NodeFlow Logger</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #333;
        }

        h1 {
            font-size: 28px;
            color: #4CAF50;
        }

        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .stat {
            padding: 10px 15px;
            background: #2a2a2a;
            border-radius: 4px;
            font-size: 12px;
            border-left: 3px solid #4CAF50;
        }

        button {
            padding: 8px 16px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }

        button:hover {
            background: #45a049;
        }

        .filters {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }

        .filter-btn {
            padding: 8px 12px;
            background: #333;
            border: 1px solid #444;
            color: #e0e0e0;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.3s;
        }

        .filter-btn.active {
            background: #4CAF50;
            border-color: #4CAF50;
            color: white;
        }

        .filter-btn:hover {
            background: #404040;
            border-color: #4CAF50;
        }

        input[type="text"] {
            padding: 8px 12px;
            background: #2a2a2a;
            border: 1px solid #444;
            color: #e0e0e0;
            border-radius: 4px;
            font-size: 12px;
        }

        input[type="text"]::placeholder {
            color: #666;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: #4CAF50;
            box-shadow: 0 0 5px rgba(76, 175, 80, 0.3);
        }

        .logs-container {
            background: #242424;
            border-radius: 4px;
            border: 1px solid #333;
            max-height: 600px;
            overflow-y: auto;
        }

        .log-entry {
            padding: 12px 15px;
            border-bottom: 1px solid #333;
            border-left: 4px solid;
            transition: background 0.2s;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .log-entry:hover {
            background: #2a2a2a;
        }

        .log-entry.input1 {
            border-left-color: #4CAF50;
        }

        .log-entry.input2 {
            border-left-color: #2196F3;
        }

        .log-entry.input3 {
            border-left-color: #FF9800;
        }

        .log-meta {
            display: flex;
            gap: 15px;
            margin-bottom: 8px;
            flex-wrap: wrap;
        }

        .log-port {
            padding: 3px 8px;
            background: #333;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }

        .log-port.input1 {
            background: #4CAF50;
            color: white;
        }

        .log-port.input2 {
            background: #2196F3;
            color: white;
        }

        .log-port.input3 {
            background: #FF9800;
            color: white;
        }

        .log-time {
            color: #999;
            font-size: 11px;
        }

        .log-data {
            background: #1a1a1a;
            padding: 10px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 150px;
            overflow-y: auto;
            word-break: break-word;
            color: #87CEEB;
        }

        .empty-state {
            padding: 40px;
            text-align: center;
            color: #666;
        }

        .status-bar {
            display: flex;
            justify-content: space-between;
            padding: 12px 15px;
            background: #2a2a2a;
            border-top: 1px solid #333;
            font-size: 12px;
        }

        .status-item {
            display: flex;
            gap: 5px;
        }

        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4CAF50;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>NodeFlow Logger</h1>
            <div class="controls">
                <div class="stat">
                    <div style="color: #999; font-size: 10px;">Logs</div>
                    <div style="font-size: 16px; font-weight: bold;" id="logCount">0</div>
                </div>
                <div class="stat">
                    <div style="color: #999; font-size: 10px;">Status</div>
                    <div style="font-size: 16px;"><span class="status-indicator"></span> Live</div>
                </div>
                <button onclick="clearLogs()">Clear</button>
                <button onclick="downloadLogs()">Export</button>
            </div>
        </header>

        <div class="filters">
            <input type="text" id="searchInput" placeholder="Search logs..." onkeyup="filterLogs()">
            <button class="filter-btn active" onclick="toggleFilter(this, 'input1')">input1</button>
            <button class="filter-btn active" onclick="toggleFilter(this, 'input2')">input2</button>
            <button class="filter-btn active" onclick="toggleFilter(this, 'input3')">input3</button>
        </div>

        <div class="logs-container" id="logsContainer">
            <div class="empty-state">Waiting for logs...</div>
        </div>

        <div class="status-bar">
            <div class="status-item">
                <span id="wsStatus" style="color: #4CAF50;">●</span>
                <span id="wsStatusText">Connected</span>
            </div>
            <div class="status-item">
                Subscribers: <span id="subscribers">0</span>
            </div>
        </div>
    </div>

    <script>
        let allLogs = [];
        let activeFilters = { input1: true, input2: true, input3: true };
        let ws = null;

        function initWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(protocol + '//' + window.location.host + '/ws');

            ws.onopen = () => {
                document.getElementById('wsStatus').textContent = '●';
                document.getElementById('wsStatus').style.color = '#4CAF50';
                document.getElementById('wsStatusText').textContent = 'Connected';
                loadInitialLogs();
            };

            ws.onmessage = (event) => {
                const log = JSON.parse(event.data);
                allLogs.unshift(log);
                updateLogsDisplay();
            };

            ws.onerror = () => {
                document.getElementById('wsStatus').textContent = '●';
                document.getElementById('wsStatus').style.color = '#FF5252';
                document.getElementById('wsStatusText').textContent = 'Error';
            };

            ws.onclose = () => {
                document.getElementById('wsStatus').textContent = '●';
                document.getElementById('wsStatus').style.color = '#FFC107';
                document.getElementById('wsStatusText').textContent = 'Disconnected';
                setTimeout(initWebSocket, 3000);
            };
        }

        function loadInitialLogs() {
            fetch('/api/logs')
                .then(r => r.json())
                .then(data => {
                    allLogs = data.logs.reverse();
                    document.getElementById('subscribers').textContent = data.subscribers;
                    updateLogsDisplay();
                })
                .catch(e => console.error('Failed to load logs:', e));
        }

        function updateLogsDisplay() {
            const container = document.getElementById('logsContainer');
            const filtered = allLogs.filter(log => {
                const portMatch = activeFilters[log.port];
                const searchMatch = document.getElementById('searchInput').value === '' ||
                    JSON.stringify(log.data).toLowerCase().includes(
                        document.getElementById('searchInput').value.toLowerCase()
                    );
                return portMatch && searchMatch;
            });

            document.getElementById('logCount').textContent = allLogs.length;

            if (filtered.length === 0) {
                container.innerHTML = '<div class="empty-state">No logs matching filters...</div>';
                return;
            }

            container.innerHTML = filtered.map(log => `
                <div class="log-entry ${log.port}">
                    <div style="flex: 1;">
                        <div class="log-meta">
                            <span class="log-port ${log.port}">${log.port}</span>
                            <span class="log-time">${new Date(log.timestamp * 1000).toLocaleTimeString()}</span>
                        </div>
                        <div class="log-data">${JSON.stringify(log.data, null, 2)}</div>
                    </div>
                </div>
            `).join('');
        }

        function toggleFilter(btn, port) {
            activeFilters[port] = !activeFilters[port];
            btn.classList.toggle('active');
            updateLogsDisplay();
        }

        function filterLogs() {
            updateLogsDisplay();
        }

        function clearLogs() {
            if (confirm('Clear all logs?')) {
                allLogs = [];
                updateLogsDisplay();
            }
        }

        function downloadLogs() {
            const json = JSON.stringify(allLogs, null, 2);
            const blob = new Blob([json], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `logs-${Date.now()}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }

        // 初始化
        initWebSocket();
    </script>
</body>
</html>"""

    async def _broadcast_to_websockets(self, log_entry: atom.LogEntry) -> None:
        """向所有 WebSocket 订阅者广播日志条目"""
        dead_subscribers = []
        for ws in self.log_buffer.subscribers:
            try:
                # 使用 atom.LogFormatter 格式化用于 WebSocket 的数据
                formatted = atom.LogFormatter.format_for_html(log_entry)
                await ws.send_json(formatted)
            except Exception:
                dead_subscribers.append(ws)

        # 清理失效的连接
        for ws in dead_subscribers:
            self.log_buffer.remove_subscriber(ws)

    def _run_web_server(self) -> None:
        """在独立线程中运行 Web 服务器"""
        try:
            uvicorn.run(
                self.app,
                host="0.0.0.0",
                port=self.web_port,
                log_level="warning"
            )
        except Exception as e:
            self.sdk.logger.error(f"Web server error: {e}")

    def _create_log_entry(self, port_name: str, data: Any) -> Dict[str, Any]:
        """创建日志条目字典"""
        # 尝试从数据中提取有用信息
        log_entry = {
            'timestamp': time.time(),
            'port': port_name,
            'data': data,
            'level': 'INFO'
        }

        # 如果数据是字典，尝试提取 seq 和 node_id
        if isinstance(data, dict):
            if 'timestamp' in data:
                log_entry['timestamp'] = data['timestamp']
            if 'seq' in data:
                log_entry['seq'] = data['seq']
            if 'node_id' in data:
                log_entry['node_id'] = data['node_id']
            # 尝试识别错误或警告级别
            if 'error' in str(data).lower() or 'exception' in str(data).lower():
                log_entry['level'] = 'ERROR'
            elif 'warning' in str(data).lower() or 'warn' in str(data).lower():
                log_entry['level'] = 'WARNING'

        return log_entry

    def run(self) -> None:
        """主循环 - 读取输入端口并处理日志"""
        # 启动 Web 服务线程
        self.web_thread = Thread(target=self._run_web_server, daemon=True)
        self.web_thread.start()

        self.sdk.logger.info(f"Logger node started")
        self.sdk.logger.info(f"Listening on 3 input ports: input1, input2, input3")
        self.sdk.logger.info(f"Web interface: http://0.0.0.0:{self.web_port}")

        # 主循环：非阻塞读取所有输入端口
        try:
            while self.running:
                for port_name, port in self.input_ports.items():
                    try:
                        # 非阻塞读取最新数据
                        data = port.recv_latest()
                        if data is not None:
                            # 创建日志条目
                            log_entry_dict = self._create_log_entry(port_name, data)

                            # 添加到缓冲区
                            log_entry = self.log_buffer.add_entry(log_entry_dict)

                            # 写入文件（如果启用）
                            if self.log_file:
                                try:
                                    self.log_file.write(
                                        atom.LogFormatter.format_for_json(log_entry) + '\n'
                                    )
                                except Exception as e:
                                    self.sdk.logger.error(f"File write error: {e}")

                            # 广播到 WebSocket 客户端
                            asyncio.run(self._broadcast_to_websockets(log_entry))

                            # 可选：控制台输出（调试用）
                            # console_msg = atom.LogFormatter.format_for_console(log_entry)
                            # self.sdk.logger.debug(console_msg)

                    except Exception as e:
                        self.sdk.logger.error(f"Error reading {port_name}: {e}")

                # 短暂延迟以降低 CPU 使用率
                time.sleep(0.01)  # 100Hz

        except KeyboardInterrupt:
            self.sdk.logger.info("Logger node shutting down...")
        except Exception as e:
            self.sdk.logger.error(f"Fatal error in main loop: {e}")
        finally:
            self.running = False
            if self.log_file:
                try:
                    self.log_file.close()
                except:
                    pass


def main():
    """节点主入口"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Creating LoggerNode instance")
        logger_node = LoggerNode(sdk)
        sdk.logger.info("Starting LoggerNode run()")
        logger_node.run()
        sdk.logger.info("LoggerNode run() completed")


if __name__ == '__main__':
    main()