#!/usr/bin/env python3
"""
轨迹可视化 Web 服务器
使用 Flask + SocketIO 实现实时数据推送
"""

import threading
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
from typing import Dict, Any, Optional

# Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'trajectory-viz-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局数据存储
current_data = {
    "field_boundary": None,
    "planned_path": None,
    "actual_trajectory": [],
    "actual_trajectory_with_heading": [],
    "metrics": {}
}

# HTML 模板（稍后创建独立文件）
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NodeFlow 轨迹可视化</title>
    <meta charset="utf-8">
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 10px;
        }
        .status {
            text-align: center;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-weight: 500;
        }
        .status.connected {
            background-color: #d4edda;
            color: #155724;
        }
        .status.disconnected {
            background-color: #f8d7da;
            color: #721c24;
        }
        #plot {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .metrics {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 20px;
        }
        .metrics h2 {
            margin-top: 0;
            color: #333;
            font-size: 1.3em;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }
        .metric-item {
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
            border-left: 4px solid #007bff;
        }
        .metric-label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }
        .metric-value {
            font-size: 1.5em;
            font-weight: bold;
            color: #333;
        }
        .metric-unit {
            font-size: 0.9em;
            color: #666;
            margin-left: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚜 NodeFlow 轨迹实时可视化</h1>
        <div id="status" class="status disconnected">⏳ 连接中...</div>

        <div id="plot"></div>

        <div class="metrics">
            <h2>📊 轨迹统计</h2>
            <div class="metric-grid" id="metrics-grid">
                <div class="metric-item">
                    <div class="metric-label">规划距离</div>
                    <div class="metric-value">
                        <span id="planned-distance">--</span>
                        <span class="metric-unit">m</span>
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">实际距离</div>
                    <div class="metric-value">
                        <span id="actual-distance">--</span>
                        <span class="metric-unit">m</span>
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">距离误差</div>
                    <div class="metric-value">
                        <span id="distance-error">--</span>
                        <span class="metric-unit">m</span>
                        (<span id="distance-error-percent">--</span>%)
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">平均横向误差</div>
                    <div class="metric-value">
                        <span id="avg-lateral-error">--</span>
                        <span class="metric-unit">m</span>
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">最大横向误差</div>
                    <div class="metric-value">
                        <span id="max-lateral-error">--</span>
                        <span class="metric-unit">m</span>
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">轨迹点数</div>
                    <div class="metric-value">
                        <span id="trajectory-points">--</span>
                        <span class="metric-unit">个</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // WebSocket 连接
        const socket = io();

        // 状态管理
        const statusDiv = document.getElementById('status');

        socket.on('connect', function() {
            statusDiv.textContent = '✅ 已连接到服务器';
            statusDiv.className = 'status connected';
        });

        socket.on('disconnect', function() {
            statusDiv.textContent = '❌ 连接已断开';
            statusDiv.className = 'status disconnected';
        });

        // 初始化 Plotly 图表
        const plotDiv = document.getElementById('plot');
        const layout = {
            title: '轨迹对比 (ENU坐标系)',
            xaxis: { title: 'X - 东向 (m)', scaleanchor: 'y', scaleratio: 1 },
            yaxis: { title: 'Y - 北向 (m)' },
            hovermode: 'closest',
            showlegend: true,
            legend: { x: 1, y: 1 },
            height: 600
        };

        // 初始化空图表
        Plotly.newPlot(plotDiv, [], layout, { responsive: true });

        // 接收数据更新
        socket.on('trajectory_update', function(data) {
            const traces = [];

            // 地块边界
            if (data.field_boundary && data.field_boundary.length >= 3) {
                const boundary = data.field_boundary;
                // 闭合多边形
                const boundaryX = boundary.map(p => p[0]).concat([boundary[0][0]]);
                const boundaryY = boundary.map(p => p[1]).concat([boundary[0][1]]);

                traces.push({
                    x: boundaryX,
                    y: boundaryY,
                    mode: 'lines',
                    fill: 'toself',
                    fillcolor: 'rgba(0, 255, 0, 0.1)',
                    line: { color: 'green', width: 2 },
                    name: '地块边界'
                });
            }

            // 规划路径
            if (data.planned_path && data.planned_path.length >= 2) {
                const path = data.planned_path;
                const pathX = path.map(p => p[0]);
                const pathY = path.map(p => p[1]);

                traces.push({
                    x: pathX,
                    y: pathY,
                    mode: 'lines+markers',
                    line: { color: 'blue', width: 2 },
                    marker: { size: 4 },
                    name: '规划路径'
                });

                // 起点和终点
                traces.push({
                    x: [pathX[0]],
                    y: [pathY[0]],
                    mode: 'markers',
                    marker: { color: 'blue', size: 12, symbol: 'circle' },
                    name: '规划起点',
                    showlegend: false
                });

                traces.push({
                    x: [pathX[pathX.length - 1]],
                    y: [pathY[pathY.length - 1]],
                    mode: 'markers',
                    marker: { color: 'blue', size: 12, symbol: 'square' },
                    name: '规划终点',
                    showlegend: false
                });
            }

            // 实际轨迹
            if (data.actual_trajectory && data.actual_trajectory.length >= 2) {
                const trajectory = data.actual_trajectory;
                const trajX = trajectory.map(p => p[0]);
                const trajY = trajectory.map(p => p[1]);

                traces.push({
                    x: trajX,
                    y: trajY,
                    mode: 'lines+markers',
                    line: { color: 'red', width: 2 },
                    marker: { size: 4 },
                    name: '实际轨迹'
                });

                // 起点和终点
                traces.push({
                    x: [trajX[0]],
                    y: [trajY[0]],
                    mode: 'markers',
                    marker: { color: 'red', size: 12, symbol: 'circle' },
                    name: '实际起点',
                    showlegend: false
                });

                traces.push({
                    x: [trajX[trajX.length - 1]],
                    y: [trajY[trajY.length - 1]],
                    mode: 'markers',
                    marker: { color: 'red', size: 12, symbol: 'square' },
                    name: '实际终点',
                    showlegend: false
                });
            }

            // 更新图表
            Plotly.react(plotDiv, traces, layout);

            // 添加航向角箭头（使用 annotations）
            if (data.actual_trajectory_with_heading && data.actual_trajectory_with_heading.length >= 2) {
                const headingData = data.actual_trajectory_with_heading;
                const annotations = [];

                // 每隔几个点绘制一个箭头（避免过于密集）
                const step = Math.max(1, Math.floor(headingData.length / 20));

                for (let i = 0; i < headingData.length; i += step) {
                    const [x, y, theta] = headingData[i];

                    // 箭头长度（米）
                    const arrowLen = 3.0;
                    const dx = Math.cos(theta) * arrowLen;
                    const dy = Math.sin(theta) * arrowLen;

                    annotations.push({
                        x: x + dx,
                        y: y + dy,
                        ax: x,
                        ay: y,
                        xref: 'x',
                        yref: 'y',
                        axref: 'x',
                        ayref: 'y',
                        showarrow: true,
                        arrowhead: 2,
                        arrowsize: 1,
                        arrowwidth: 2,
                        arrowcolor: 'red',
                        opacity: 0.6
                    });
                }

                // 更新 layout 添加箭头
                const newLayout = Object.assign({}, layout, { annotations: annotations });
                Plotly.relayout(plotDiv, newLayout);
            }

            // 更新统计信息
            updateMetrics(data.metrics || {});
        });

        function updateMetrics(metrics) {
            document.getElementById('planned-distance').textContent =
                metrics.planned_distance_m || '--';
            document.getElementById('actual-distance').textContent =
                metrics.actual_distance_m || '--';
            document.getElementById('distance-error').textContent =
                metrics.distance_error_m || '--';
            document.getElementById('distance-error-percent').textContent =
                metrics.distance_error_percent || '--';
            document.getElementById('avg-lateral-error').textContent =
                metrics.avg_lateral_error_m || '--';
            document.getElementById('max-lateral-error').textContent =
                metrics.max_lateral_error_m || '--';
            document.getElementById('trajectory-points').textContent =
                metrics.trajectory_points || '--';
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """主页"""
    return render_template_string(HTML_TEMPLATE)


@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f"[WebSocket] 客户端已连接")
    # 发送当前数据
    emit('trajectory_update', current_data)


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print(f"[WebSocket] 客户端已断开")


def update_trajectory_data(field_boundary=None, planned_path=None,
                          actual_trajectory=None, actual_trajectory_with_heading=None,
                          metrics=None):
    """
    更新轨迹数据并推送到所有客户端

    Args:
        field_boundary: 地块边界 [(x, y), ...]
        planned_path: 规划路径 [(x, y), ...]
        actual_trajectory: 实际轨迹 [(x, y), ...]
        actual_trajectory_with_heading: 带航向角的实际轨迹 [(x, y, theta), ...]
        metrics: 统计指标字典
    """
    global current_data

    if field_boundary is not None:
        current_data["field_boundary"] = field_boundary

    if planned_path is not None:
        current_data["planned_path"] = planned_path

    if actual_trajectory is not None:
        current_data["actual_trajectory"] = actual_trajectory

    if actual_trajectory_with_heading is not None:
        current_data["actual_trajectory_with_heading"] = actual_trajectory_with_heading

    if metrics is not None:
        current_data["metrics"] = metrics

    # 推送到所有连接的客户端
    socketio.emit('trajectory_update', current_data)


def start_web_server(host='0.0.0.0', port=5000):
    """
    启动 Web 服务器（在单独的线程中）

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        服务器线程对象
    """
    def run_server():
        print(f"🌐 轨迹可视化服务器启动:")
        print(f"   地址: http://{host}:{port}")
        print(f"   请在浏览器中打开此地址查看实时轨迹")
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

    # daemon=True 表示当主程序退出时，此线程会自动被终止
    # 这确保了 NodeFlow 节点关闭时，Web 服务器也会关闭
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread


def stop_web_server():
    """
    停止 Web 服务器（优雅关闭）

    注意：由于使用了 daemon 线程，大多数情况下不需要手动调用此函数，
    NodeFlow 节点退出时会自动终止 Web 服务器线程。
    """
    print("🔴 正在关闭 Web 服务器...")
    socketio.stop()
    print("✅ Web 服务器已关闭")
