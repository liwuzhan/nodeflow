#!/usr/bin/env python3
"""
轨迹可视化 Web 服务器（工具模块）

功能：
- 提供 Flask + SocketIO Web服务器
- 实时推送轨迹数据到浏览器
- Plotly.js 交互式可视化

职责：纯粹的Web服务，无业务逻辑
"""

import threading
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
from typing import Dict, Any, Optional, List, Tuple

# Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'trajectory-viz-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局数据存储（简单内存缓存）
current_data = {
    "field_boundary": None,
    "planned_path": None,
    "path_zones": [],
    "operation_segments": [],
    "actual_trajectory": [],
    "actual_trajectory_with_heading": [],
    "metrics": {},
    "next_point": None,
    "velocity_cmd": None,
    "tillage_cmd": None,
    "tillage_status": None,
    "path_progress": None,
    "replay_samples": [],
    "replay_events": [],
    "coverage_overlay": {}
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
        .dashboard {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .panel {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 14px 16px;
        }
        .panel-label {
            font-size: 0.82em;
            color: #666;
            margin-bottom: 6px;
        }
        .panel-value {
            font-size: 1.25em;
            font-weight: 700;
            color: #222;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .panel-sub {
            color: #666;
            font-size: 0.86em;
            margin-top: 6px;
        }
        #plot,
        #speed-plot,
        #factor-plot {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 16px;
            margin-bottom: 20px;
        }
        .plot-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
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
        @media (max-width: 1000px) {
            .dashboard,
            .plot-grid {
                grid-template-columns: 1fr 1fr;
            }
        }
        @media (max-width: 680px) {
            .dashboard,
            .plot-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚜 NodeFlow 轨迹实时可视化</h1>
        <div id="status" class="status disconnected">⏳ 连接中...</div>

        <div class="dashboard">
            <div class="panel">
                <div class="panel-label">底盘状态</div>
                <div class="panel-value" id="track-state">--</div>
                <div class="panel-sub" id="speed-state">v -- m/s, w -- rad/s</div>
            </div>
            <div class="panel">
                <div class="panel-label">前瞻目标</div>
                <div class="panel-value" id="waypoint-state">--</div>
                <div class="panel-sub" id="turn-state">turn -- deg</div>
            </div>
            <div class="panel">
                <div class="panel-label">路径段</div>
                <div class="panel-value" id="segment-state">--</div>
                <div class="panel-sub" id="error-state">cte -- m, heading -- deg</div>
            </div>
            <div class="panel">
                <div class="panel-label">机具状态</div>
                <div class="panel-value" id="implement-state">--</div>
                <div class="panel-sub" id="hitch-state">PTO --, hitch --</div>
            </div>
            <div class="panel">
                <div class="panel-label">覆盖复盘</div>
                <div class="panel-value" id="coverage-state">--</div>
                <div class="panel-sub" id="covered-area-state">area -- m2, seg --, samples --/--</div>
            </div>
        </div>

        <div id="plot"></div>
        <div class="plot-grid">
            <div id="speed-plot"></div>
            <div id="factor-plot"></div>
        </div>

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
                <div class="metric-item">
                    <div class="metric-label">机具幅宽</div>
                    <div class="metric-value">
                        <span id="implement-width">--</span>
                        <span class="metric-unit">m</span>
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">已覆盖面积</div>
                    <div class="metric-value">
                        <span id="covered-area">--</span>
                        <span class="metric-unit">m²</span>
                    </div>
                </div>
                <div class="metric-item">
                    <div class="metric-label">覆盖率</div>
                    <div class="metric-value">
                        <span id="coverage-rate">--</span>
                        <span class="metric-unit">%</span>
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
        const speedPlotDiv = document.getElementById('speed-plot');
        const factorPlotDiv = document.getElementById('factor-plot');
        const layout = {
            title: '轨迹对比 (ENU坐标系)',
            xaxis: { title: 'X - 东向 (m)', scaleanchor: 'y', scaleratio: 1 },
            yaxis: { title: 'Y - 北向 (m)' },
            hovermode: 'closest',
            showlegend: true,
            legend: { x: 1, y: 1 },
            height: 600
        };
        const speedLayout = {
            title: '速度与预判转角',
            xaxis: { title: '时间 (s)' },
            yaxis: { title: '速度 / 角速度' },
            yaxis2: { title: '转角 (deg)', overlaying: 'y', side: 'right' },
            hovermode: 'x unified',
            showlegend: true,
            height: 360
        };
        const factorLayout = {
            title: '减速因子与机具状态',
            xaxis: { title: '时间 (s)' },
            yaxis: { title: '因子 / PTO', range: [-0.05, 1.05] },
            yaxis2: { title: '悬挂高度', overlaying: 'y', side: 'right', range: [-0.05, 1.05] },
            hovermode: 'x unified',
            showlegend: true,
            height: 360
        };

        // 初始化空图表
        Plotly.newPlot(plotDiv, [], layout, { responsive: true });
        Plotly.newPlot(speedPlotDiv, [], speedLayout, { responsive: true });
        Plotly.newPlot(factorPlotDiv, [], factorLayout, { responsive: true });

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

            // 已覆盖区域（机具作业 footprint，近似）
            if (data.coverage_overlay && data.coverage_overlay.polygons) {
                data.coverage_overlay.polygons.forEach((poly, idx) => {
                    if (!poly || poly.length < 3) {
                        return;
                    }
                    const xs = poly.map(p => p[0]).concat([poly[0][0]]);
                    const ys = poly.map(p => p[1]).concat([poly[0][1]]);
                    traces.push({
                        x: xs,
                        y: ys,
                        mode: 'lines',
                        fill: 'toself',
                        fillcolor: 'rgba(22, 163, 74, 0.18)',
                        line: { color: 'rgba(22, 163, 74, 0.25)', width: 1 },
                        name: idx === 0 ? '已覆盖区域' : '已覆盖区域',
                        showlegend: idx === 0,
                        hoverinfo: 'skip'
                    });
                });
            }

            // 当前前瞻目标点
            if (data.next_point && data.next_point.x !== undefined && data.next_point.y !== undefined) {
                traces.push({
                    x: [data.next_point.x],
                    y: [data.next_point.y],
                    mode: 'markers',
                    marker: { color: '#111827', size: 12, symbol: 'x' },
                    name: '当前目标点'
                });
            }

            // 复盘事件点
            if (data.replay_events && data.replay_events.length > 0) {
                const events = data.replay_events.filter(e => e.x !== null && e.y !== null);
                if (events.length > 0) {
                    traces.push({
                        x: events.map(e => e.x),
                        y: events.map(e => e.y),
                        text: events.map(e => e.label),
                        mode: 'markers',
                        marker: {
                            color: events.map(e => eventColor(e.kind)),
                            size: 10,
                            symbol: 'diamond'
                        },
                        hovertemplate: '%{text}<br>x=%{x:.2f}<br>y=%{y:.2f}<extra>事件</extra>',
                        name: '控制事件'
                    });
                }
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
            updateStatusPanels(data);
            updateReplayPlots(data.replay_samples || []);
        });

        function fmt(value, digits = 2) {
            if (value === null || value === undefined || Number.isNaN(Number(value))) {
                return '--';
            }
            return Number(value).toFixed(digits);
        }

        function valueOrDash(value) {
            if (value === null || value === undefined || Number.isNaN(Number(value))) {
                return '--';
            }
            return value;
        }

        function textOrDash(value) {
            return value || '--';
        }

        function eventColor(kind) {
            const colors = {
                track_status: '#7c3aed',
                waypoint_mode: '#2563eb',
                segment: '#0891b2',
                tillage_state: '#16a34a',
                pto: '#dc2626',
                turn_preview: '#ea580c'
            };
            return colors[kind] || '#374151';
        }

        function updateStatusPanels(data) {
            const velocity = data.velocity_cmd || {};
            const nextPoint = data.next_point || {};
            const progress = data.path_progress || {};
            const tillage = data.tillage_status || data.tillage_cmd || {};
            const metrics = data.metrics || {};
            const coverage = data.coverage_overlay || {};

            document.getElementById('track-state').textContent =
                textOrDash(velocity.status || 'tracking');
            document.getElementById('speed-state').textContent =
                `v ${fmt(velocity.linear_velocity)} m/s, w ${fmt(velocity.angular_velocity)} rad/s`;

            document.getElementById('waypoint-state').textContent =
                `${textOrDash(nextPoint.mode)} #${nextPoint.index ?? '--'}`;
            document.getElementById('turn-state').textContent =
                `turn ${fmt(nextPoint.upcoming_turn_angle_deg, 1)} deg, view ${nextPoint.in_view_count ?? '--'}`;

            document.getElementById('segment-state').textContent =
                textOrDash(progress.segment_id || progress.segment_type || nextPoint.zone);
            document.getElementById('error-state').textContent =
                `cte ${fmt(progress.cross_track_error_m)} m, heading ${fmt(progress.heading_error_deg, 1)} deg`;

            document.getElementById('implement-state').textContent =
                textOrDash(tillage.state);
            document.getElementById('hitch-state').textContent =
                `PTO ${tillage.pto_on === true ? 'ON' : tillage.pto_on === false ? 'OFF' : '--'}, hitch ${fmt(tillage.hitch_height)}`;

            document.getElementById('coverage-state').textContent =
                `${fmt(metrics.coverage_rate_percent, 1)}%`;
            document.getElementById('covered-area-state').textContent =
                `area ${fmt(metrics.covered_area_m2, 1)} m2, seg ${coverage.active_segments ?? '--'}, samples ${coverage.working_sample_count ?? '--'}/${coverage.sample_count ?? '--'}, active ${coverage.latest_active === true ? 'Y' : coverage.latest_active === false ? 'N' : '--'}`;
        }

        function updateReplayPlots(samples) {
            if (!samples.length) {
                Plotly.react(speedPlotDiv, [], speedLayout);
                Plotly.react(factorPlotDiv, [], factorLayout);
                return;
            }

            const t0 = samples[0].timestamp || 0;
            const times = samples.map(s => (s.timestamp || 0) - t0);

            const speedTraces = [
                {
                    x: times,
                    y: samples.map(s => s.linear_velocity),
                    mode: 'lines',
                    line: { color: '#dc2626', width: 2 },
                    name: '线速度'
                },
                {
                    x: times,
                    y: samples.map(s => s.angular_velocity),
                    mode: 'lines',
                    line: { color: '#2563eb', width: 2 },
                    name: '角速度'
                },
                {
                    x: times,
                    y: samples.map(s => s.upcoming_turn_angle_deg),
                    mode: 'lines',
                    yaxis: 'y2',
                    line: { color: '#ea580c', width: 2, dash: 'dot' },
                    name: '预判转角'
                }
            ];

            const factorTraces = [
                {
                    x: times,
                    y: samples.map(s => s.speed_factor),
                    mode: 'lines',
                    line: { color: '#111827', width: 2 },
                    name: '总减速因子'
                },
                {
                    x: times,
                    y: samples.map(s => s.turn_factor),
                    mode: 'lines',
                    line: { color: '#ea580c', width: 1.5 },
                    name: '转角因子'
                },
                {
                    x: times,
                    y: samples.map(s => s.view_factor),
                    mode: 'lines',
                    line: { color: '#2563eb', width: 1.5 },
                    name: '视野因子'
                },
                {
                    x: times,
                    y: samples.map(s => s.pto_on === true ? 1 : s.pto_on === false ? 0 : null),
                    mode: 'lines',
                    line: { color: '#16a34a', width: 2, shape: 'hv' },
                    name: 'PTO'
                },
                {
                    x: times,
                    y: samples.map(s => s.hitch_height),
                    mode: 'lines',
                    yaxis: 'y2',
                    line: { color: '#9333ea', width: 2 },
                    name: '悬挂高度'
                }
            ];

            Plotly.react(speedPlotDiv, speedTraces, speedLayout);
            Plotly.react(factorPlotDiv, factorTraces, factorLayout);
        }

        function updateMetrics(metrics) {
            document.getElementById('planned-distance').textContent =
                valueOrDash(metrics.planned_distance_m);
            document.getElementById('actual-distance').textContent =
                valueOrDash(metrics.actual_distance_m);
            document.getElementById('distance-error').textContent =
                valueOrDash(metrics.distance_error_m);
            document.getElementById('distance-error-percent').textContent =
                valueOrDash(metrics.distance_error_percent);
            document.getElementById('avg-lateral-error').textContent =
                valueOrDash(metrics.avg_lateral_error_m);
            document.getElementById('max-lateral-error').textContent =
                valueOrDash(metrics.max_lateral_error_m);
            document.getElementById('trajectory-points').textContent =
                valueOrDash(metrics.trajectory_points);
            document.getElementById('implement-width').textContent =
                valueOrDash(metrics.implement_width_m);
            document.getElementById('covered-area').textContent =
                valueOrDash(metrics.covered_area_m2);
            document.getElementById('coverage-rate').textContent =
                valueOrDash(metrics.coverage_rate_percent);
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
                          path_zones=None, operation_segments=None,
                          actual_trajectory=None, actual_trajectory_with_heading=None,
                          metrics=None, next_point=None, velocity_cmd=None,
                          tillage_cmd=None, tillage_status=None, path_progress=None,
                          replay_samples=None, replay_events=None,
                          coverage_overlay=None):
    """
    更新轨迹数据并推送到所有客户端

    Args:
        field_boundary: 地块边界 [(x, y), ...]
        planned_path: 规划路径 [(x, y), ...]
        path_zones: 每个路径点的作业区域标注
        operation_segments: 作业段语义
        actual_trajectory: 实际轨迹 [(x, y), ...]
        actual_trajectory_with_heading: 带航向角的实际轨迹 [(x, y, theta), ...]
        metrics: 统计指标字典
    """
    global current_data

    if field_boundary is not None:
        current_data["field_boundary"] = field_boundary

    if planned_path is not None:
        current_data["planned_path"] = planned_path

    if path_zones is not None:
        current_data["path_zones"] = path_zones

    if operation_segments is not None:
        current_data["operation_segments"] = operation_segments

    if actual_trajectory is not None:
        current_data["actual_trajectory"] = actual_trajectory

    if actual_trajectory_with_heading is not None:
        current_data["actual_trajectory_with_heading"] = actual_trajectory_with_heading

    if metrics is not None:
        current_data["metrics"] = metrics

    if next_point is not None:
        current_data["next_point"] = next_point

    if velocity_cmd is not None:
        current_data["velocity_cmd"] = velocity_cmd

    if tillage_cmd is not None:
        current_data["tillage_cmd"] = tillage_cmd

    if tillage_status is not None:
        current_data["tillage_status"] = tillage_status

    if path_progress is not None:
        current_data["path_progress"] = path_progress

    if replay_samples is not None:
        current_data["replay_samples"] = replay_samples

    if replay_events is not None:
        current_data["replay_events"] = replay_events

    if coverage_overlay is not None:
        current_data["coverage_overlay"] = coverage_overlay

    # 推送到所有连接的客户端
    socketio.emit('trajectory_update', current_data)


def start_web_server(host='0.0.0.0', port=8080):
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
