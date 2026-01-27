#!/usr/bin/env python3
"""
地块规划 Web 服务器（工具模块）

功能：
- 提供 Flask + SocketIO Web服务器
- 高德地图 API 界面绘制地块
- GPS 参考点设置
- 地块配置保存/加载
- 坐标转换接口

职责：纯粹的Web服务，无业务逻辑
"""

import os
import json
import threading
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
from typing import Dict, Any, Optional, List

# 导入坐标转换算法
from atom import gps_to_enu, enu_to_gps, convert_boundary_gps_to_enu, convert_boundary_enu_to_gps, calculate_polygon_area, calculate_perimeter

# Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'parcel-planner-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 数据目录
DATA_DIR = Path(__file__).parent / 'data' / 'parcels'

# 配置文件路径
CONFIG_FILE = Path(__file__).parent / 'config.json'


def load_config() -> Dict[str, Any]:
    """
    加载配置文件

    配置优先级：命令行参数 > 环境变量 > 配置文件 > 默认值

    Returns:
        配置字典
    """
    config = {
        'amap_api_key': '',
        'web_host': '0.0.0.0',
        'web_port': 8081
    }

    # 从配置文件读取
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"警告: 读取配置文件失败: {e}")

    # 环境变量优先级更高
    if os.environ.get('AMAP_API_KEY'):
        config['amap_api_key'] = os.environ.get('AMAP_API_KEY')

    return config

# 当前绘制状态
current_state = {
    "ref_point": None,  # {"lon": xxx, "lat": xxx}
    "boundary_gps": [],  # [[lon, lat], ...]
    "boundary_enu": [],  # [[x, y], ...]
    "vehicle": {
        "implement_width_m": 2.0,
        "overlap_ratio": 0.1,
        "path_inset_m": 0.5
    },
    "current_parcel": None  # 当前加载的地块名称
}


def get_parcels_list() -> List[Dict[str, Any]]:
    """获取已保存的地块列表"""
    parcels = []
    if not DATA_DIR.exists():
        return parcels

    for file_path in DATA_DIR.glob('*.json'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                parcels.append({
                    'name': data.get('name', file_path.stem),
                    'description': data.get('description', ''),
                    'updated_at': data.get('updated_at', ''),
                    'file_name': file_path.name
                })
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    return parcels


def load_parcel_data(name: str) -> Optional[Dict[str, Any]]:
    """加载指定地块数据"""
    file_path = DATA_DIR / f'{name}.json'
    if not file_path.exists():
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading parcel {name}: {e}")
        return None


def save_parcel_data(name: str, data: Dict[str, Any]) -> bool:
    """保存地块数据"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # 更新时间戳
        from datetime import datetime
        now = datetime.now().isoformat()
        data['updated_at'] = now
        if 'created_at' not in data:
            data['created_at'] = now

        file_path = DATA_DIR / f'{name}.json'
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"Error saving parcel {name}: {e}")
        return False


def delete_parcel_data(name: str) -> bool:
    """删除地块数据"""
    try:
        file_path = DATA_DIR / f'{name}.json'
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    except Exception as e:
        print(f"Error deleting parcel {name}: {e}")
        return False


# HTML 模板
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>地块规划工具 - NodeFlow</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script src="https://webapi.amap.com/maps?v=2.0&key={{ amap_api_key }}"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 {
            font-size: 1.5em;
            margin-bottom: 5px;
        }
        .header .status {
            font-size: 0.9em;
            opacity: 0.9;
        }
        .main-container {
            display: flex;
            height: calc(100vh - 70px);
        }
        .sidebar {
            width: 320px;
            background: white;
            padding: 20px;
            overflow-y: auto;
            box-shadow: 2px 0 4px rgba(0,0,0,0.1);
        }
        .map-container {
            flex: 1;
            position: relative;
        }
        #map {
            width: 100%;
            height: 100%;
        }
        .section {
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }
        .section:last-child {
            border-bottom: none;
        }
        .section-title {
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
            font-size: 1em;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            font-size: 0.85em;
            color: #666;
            margin-bottom: 5px;
        }
        .form-group input,
        .form-group textarea {
            width: 100%;
            padding: 8px 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .form-group input:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        .form-row {
            display: flex;
            gap: 10px;
        }
        .form-row .form-group {
            flex: 1;
        }
        button {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #667eea;
            color: white;
        }
        .btn-primary:hover {
            background: #5568d3;
        }
        .btn-success {
            background: #10b981;
            color: white;
        }
        .btn-success:hover {
            background: #059669;
        }
        .btn-danger {
            background: #ef4444;
            color: white;
        }
        .btn-danger:hover {
            background: #dc2626;
        }
        .btn-secondary {
            background: #6b7280;
            color: white;
        }
        .btn-secondary:hover {
            background: #4b5563;
        }
        .btn-group {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .parcel-list {
            list-style: none;
        }
        .parcel-item {
            padding: 10px;
            background: #f9fafb;
            border-radius: 4px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .parcel-item:hover {
            background: #f3f4f6;
        }
        .parcel-item.active {
            background: #e0e7ff;
            border-left: 3px solid #667eea;
        }
        .parcel-name {
            font-weight: 500;
            color: #333;
        }
        .parcel-desc {
            font-size: 0.8em;
            color: #666;
            margin-top: 3px;
        }
        .info-box {
            background: #f0fdf4;
            border: 1px solid #86efac;
            border-radius: 4px;
            padding: 10px;
            font-size: 0.85em;
            color: #166534;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
        }
        .info-label {
            color: #6b7280;
        }
        .info-value {
            font-weight: 500;
        }
        .map-controls {
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            z-index: 100;
        }
        .map-controls button {
            display: block;
            width: 100%;
            margin-bottom: 5px;
        }
        .map-controls button:last-child {
            margin-bottom: 0;
        }
        .coordinate-display {
            position: absolute;
            bottom: 10px;
            left: 10px;
            background: rgba(255,255,255,0.95);
            padding: 10px;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            z-index: 100;
            font-size: 0.85em;
        }
        .coordinate-display .coord-row {
            display: flex;
            gap: 15px;
        }
        .coordinate-display .coord-item {
            display: flex;
            gap: 5px;
        }
        .coordinate-display .coord-label {
            color: #6b7280;
        }
        .coordinate-display .coord-value {
            font-weight: 500;
            color: #333;
        }
        .alert {
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 10px;
            font-size: 0.85em;
        }
        .alert-info {
            background: #dbeafe;
            color: #1e40af;
        }
        .alert-success {
            background: #d1fae5;
            color: #065f46;
        }
        .alert-warning {
            background: #fef3c7;
            color: #92400e;
        }
        .alert-error {
            background: #fee2e2;
            color: #991b1b;
        }
        .hidden {
            display: none;
        }
        .mode-badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 500;
        }
        .mode-badge.idle {
            background: #e5e7eb;
            color: #6b7280;
        }
        .mode-badge.draw {
            background: #dbeafe;
            color: #1e40af;
        }
        .mode-badge.hole {
            background: #fee2e2;
            color: #991b1b;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚜 地块规划工具</h1>
        <div class="status" style="display:flex;align-items:center;gap:10px;">
            <span id="connection-status">⏳ 连接中...</span>
            <span id="mode-display" class="mode-badge idle">👆 选择模式</span>
        </div>
    </div>

    <div class="main-container">
        <div class="sidebar">
            <!-- 地块名称 -->
            <div class="section">
                <div class="section-title">📦 地块信息</div>
                <div class="form-group">
                    <label>地块名称</label>
                    <input type="text" id="parcel-name" value="default" placeholder="输入地块名称">
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="parcel-desc" rows="2" placeholder="地块描述（可选）"></textarea>
                </div>
            </div>

            <!-- GPS 参考点 -->
            <div class="section">
                <div class="section-title">📍 GPS 参考点（原点）</div>
                <div id="ref-point-alert" class="alert alert-warning">
                    请先设置 GPS 参考点
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>经度</label>
                        <input type="number" id="ref-lon" step="0.000001" placeholder="121.xxxxx">
                    </div>
                    <div class="form-group">
                        <label>纬度</label>
                        <input type="number" id="ref-lat" step="0.000001" placeholder="31.xxxxx">
                    </div>
                </div>
                <div class="btn-group">
                    <button class="btn-primary" onclick="setRefPointFromInput()">从输入设置</button>
                    <button class="btn-secondary" onclick="enableRefPointPick()">📍 在地图选点</button>
                </div>
            </div>

            <!-- 车辆配置 -->
            <div class="section">
                <div class="section-title">🚛 车辆配置</div>
                <div class="form-row">
                    <div class="form-group">
                        <label>作业幅宽 (m)</label>
                        <input type="number" id="implement-width" value="2.0" step="0.1" min="0.1">
                    </div>
                    <div class="form-group">
                        <label>重叠率</label>
                        <input type="number" id="overlap-ratio" value="0.1" step="0.01" min="0" max="0.5">
                    </div>
                </div>
                <div class="form-group">
                    <label>路径内缩 (m)</label>
                    <input type="number" id="path-inset" value="0.5" step="0.1" min="0">
                </div>
            </div>

            <!-- 地块统计 -->
            <div class="section" id="stats-section">
                <div class="section-title">📊 地块统计</div>
                <div class="info-box">
                    <div class="info-row">
                        <span class="info-label">边界点数:</span>
                        <span class="info-value" id="stat-points">0</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">孔洞数量:</span>
                        <span class="info-value" id="stat-holes">0</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">面积:</span>
                        <span class="info-value" id="stat-area">-- m²</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">周长:</span>
                        <span class="info-value" id="stat-perimeter">-- m</span>
                    </div>
                </div>
            </div>

            <!-- 操作按钮 -->
            <div class="section">
                <div class="section-title">💾 操作</div>
                <div class="btn-group" style="margin-bottom: 10px;">
                    <button class="btn-success" onclick="saveParcel()">保存地块</button>
                    <button class="btn-danger" onclick="clearBoundary()">清除绘制</button>
                </div>
                <button class="btn-secondary" onclick="refreshParcels()" style="width:100%">🔄 刷新列表</button>
            </div>

            <!-- 已保存的地块 -->
            <div class="section">
                <div class="section-title">📂 已保存的地块</div>
                <ul class="parcel-list" id="parcel-list">
                    <li style="color:#999;font-size:0.9em;">加载中...</li>
                </ul>
            </div>
        </div>

        <div class="map-container">
            <div id="map"></div>

            <div class="map-controls">
                <button class="btn-primary" onclick="enableDrawMode()">✏️ 绘制外边界</button>
                <button class="btn-secondary" onclick="enableHoleMode()">🕳️ 绘制孔洞</button>
                <button class="btn-secondary" onclick="finishDraw()">✓ 完成当前</button>
                <button class="btn-secondary" onclick="finishHole()">✓ 完成孔洞</button>
                <button class="btn-secondary" onclick="undoPoint()">↩️ 撤外边点</button>
                <button class="btn-secondary" onclick="undoHolePoint()">↩️ 撤孔洞点</button>
                <button class="btn-danger" onclick="clearHoles()">🗑️ 清孔洞</button>
                <button class="btn-secondary" onclick="fitView()">🎯 适应视图</button>
            </div>

            <div class="coordinate-display">
                <div class="coord-row">
                    <div class="coord-item">
                        <span class="coord-label">GPS:</span>
                        <span class="coord-value" id="cursor-gps">--</span>
                    </div>
                    <div class="coord-item">
                        <span class="coord-label">ENU:</span>
                        <span class="coord-value" id="cursor-enu">--</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // 状态
        let map = null;
        let socket = null;
        let refPoint = null;  // {lon, lat}
        let boundaryMarkers = [];
        let boundaryPolyline = null;
        let boundaryPolygon = null;  // 外边界多边形
        let refMarker = null;
        let isDrawMode = false;
        let isPickRefMode = false;
        let isHoleMode = false;  // 是否在绘制孔洞模式
        let currentHole = [];  // 当前正在绘制的孔洞
        let holes = [];  // 已完成的孔洞列表 [[markers...], ...]
        let holePolygons = [];  // 孔洞多边形对象
        let currentParcel = null;
        let parcels = [];

        // 高德地图 API Key（从服务端获取）
        const AMAP_API_KEY = '{{ amap_api_key }}';

        // 初始化
        document.addEventListener('DOMContentLoaded', function() {
            if (!AMAP_API_KEY || AMAP_API_KEY === '' || AMAP_API_KEY.includes('your-api-key')) {
                document.getElementById('map').innerHTML = `
                    <div style="padding:40px;text-align:center;">
                        <h3 style="color:#ef4444;">⚠️ 未设置高德地图 API Key</h3>
                        <p style="color:#666;margin-top:10px;">请设置环境变量 AMAP_API_KEY 或在 node.yaml 中配置 amap_api_key 参数</p>
                        <p style="color:#666;margin-top:10px;">免费申请: https://console.amap.com/dev/key/app</p>
                    </div>
                `;
                return;
            }
            initMap();
            initSocket();
        });

        function initMap() {
            map = new AMap.Map('map', {
                zoom: 15,
                center: [121.5, 31.2],
                mapStyle: 'amap://styles/normal'
            });

            // 地图点击事件
            map.on('click', function(e) {
                const lnglat = e.lnglat;
                updateCursorDisplay(lnglat.lng, lnglat.lat);

                if (isPickRefMode) {
                    setRefPoint(lnglat.lng, lnglat.lat);
                    isPickRefMode = false;
                    document.body.style.cursor = 'default';
                } else if (isHoleMode && refPoint) {
                    // 孔洞绘制模式
                    addHolePoint(lnglat.lng, lnglat.lat);
                } else if (isDrawMode && refPoint) {
                    // 外边界绘制模式
                    addBoundaryPoint(lnglat.lng, lnglat.lat);
                }
            });

            // 鼠标移动事件
            map.on('mousemove', function(e) {
                updateCursorDisplay(e.lnglat.lng, e.lnglat.lat);
            });
        }

        function initSocket() {
            socket = io();

            socket.on('connect', function() {
                document.getElementById('connection-status').textContent = '✅ 已连接';
                refreshParcels();
            });

            socket.on('disconnect', function() {
                document.getElementById('connection-status').textContent = '❌ 连接断开';
            });

            socket.on('parcel_update', function(data) {
                if (data.ref_point) {
                    updateRefPointDisplay(data.ref_point);
                }
                if (data.boundary_enu) {
                    updateBoundaryDisplay(data.boundary_enu);
                    updateStats(data);
                }
                if (data.parcels) {
                    parcels = data.parcels;
                    renderParcelList();
                }
            });

            socket.on('parcel_loaded', function(data) {
                loadParcelData(data);
            });

            socket.on('parcel_deleted', function(data) {
                if (data.name === currentParcel) {
                    currentParcel = null;
                }
                refreshParcels();
            });
        }

        function updateCursorDisplay(lon, lat) {
            document.getElementById('cursor-gps').textContent =
                `${lon.toFixed(6)}, ${lat.toFixed(6)}`;

            if (refPoint) {
                // 发送到服务端计算 ENU
                socket.emit('convert_to_enu', {
                    lon: lon,
                    lat: lat,
                    ref_lon: refPoint.lon,
                    ref_lat: refPoint.lat
                });
            }
        }

        socket.on('enu_result', function(data) {
            document.getElementById('cursor-enu').textContent =
                `${data.x.toFixed(2)}, ${data.y.toFixed(2)}m`;
        });

        function setRefPointFromInput() {
            const lon = parseFloat(document.getElementById('ref-lon').value);
            const lat = parseFloat(document.getElementById('ref-lat').value);

            if (isNaN(lon) || isNaN(lat)) {
                alert('请输入有效的经纬度');
                return;
            }

            if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
                alert('经纬度范围无效');
                return;
            }

            setRefPoint(lon, lat);
        }

        function enableRefPointPick() {
            isPickRefMode = true;
            document.body.style.cursor = 'crosshair';
            alert('请在地图上点击选择参考点位置');
        }

        function setRefPoint(lon, lat) {
            refPoint = {lon: lon, lat: lat};

            // 更新输入框
            document.getElementById('ref-lon').value = lon.toFixed(6);
            document.getElementById('ref-lat').value = lat.toFixed(6);

            // 更新地图标记
            if (refMarker) {
                refMarker.setMap(null);
            }

            refMarker = new AMap.Marker({
                position: [lon, lat],
                icon: new AMap.Icon({
                    size: new AMap.Size(32, 32),
                    image: 'data:image/svg+xml;base64,PHHBzB3b3JuZXJzIHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iI0ZGNzgwMCI+PHBhdGggZD0iTTEyIDJDOC4xNCAyIDUgNS4xNCA1IDljMCA1LjI1IDcgMTMgNyAxM3MtNy03Ljc1LTctMTNjMC0zLjg2IDMuMTQtNyA3LTd6bTAgOWMtMS4xIDAtMi0uOS0yLTJzLjktMiAyLTIgMiAuOSAyIDItLjkgMi0yIDJ6Ii8+PC9zdmc+',
                    imageOffset: new AMap.Pixel(-16, -32)
                }),
                title: 'GPS参考点（原点）'
            });
            refMarker.setMap(map);

            // 隐藏警告
            document.getElementById('ref-point-alert').className = 'alert alert-success';
            document.getElementById('ref-point-alert').textContent = `✓ 参考点已设置: ${lon.toFixed(6)}, ${lat.toFixed(6)}`;

            // 发送到服务端
            socket.emit('set_ref_point', {lon: lon, lat: lat});

            // 重新计算现有边界的 ENU 坐标
            recalcENU();
        }

        function updateRefPointDisplay(refPointData) {
            refPoint = refPointData;
            document.getElementById('ref-lon').value = refPointData.lon.toFixed(6);
            document.getElementById('ref-lat').value = refPointData.lat.toFixed(6);

            if (refMarker) {
                refMarker.setMap(null);
            }

            refMarker = new AMap.Marker({
                position: [refPointData.lon, refPointData.lat],
                icon: new AMap.Icon({
                    size: new AMap.Size(32, 32),
                    image: 'data:image/svg+xml;base64,PHHBzB3b3JuZXJzIHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iI0ZGNzgwMCI+PHBhdGggZD0iTTEyIDJDOC4xNCAyIDUgNS4xNCA1IDljMCA1LjI1IDcgMTMgNyAxM3MtNy03Ljc1LTctMTNjMC0zLjg2IDMuMTQtNyA3LTd6bTAgOWMtMS4xIDAtMi0uOS0yLTJzLjktMiAyLTIgMiAuOSAyIDItLjkgMi0yIDJ6Ii8+PC9zdmc+',
                    imageOffset: new AMap.Pixel(-16, -32)
                }),
                title: 'GPS参考点（原点）'
            });
            refMarker.setMap(map);
        }

        function enableDrawMode() {
            if (!refPoint) {
                alert('请先设置 GPS 参考点');
                return;
            }
            isDrawMode = true;
            isHoleMode = false;
            document.body.style.cursor = 'crosshair';
            updateModeDisplay();
        }

        function enableHoleMode() {
            if (!refPoint) {
                alert('请先设置 GPS 参考点');
                return;
            }
            if (boundaryMarkers.length < 3) {
                alert('请先绘制外边界（至少3个点）');
                return;
            }
            isHoleMode = true;
            isDrawMode = false;
            currentHole = [];
            document.body.style.cursor = 'crosshair';
            updateModeDisplay();
        }

        function finishDraw() {
            isDrawMode = false;
            isPickRefMode = false;
            isHoleMode = false;
            document.body.style.cursor = 'default';
            updateModeDisplay();
        }

        function finishHole() {
            if (currentHole.length < 3) {
                alert('孔洞至少需要3个点');
                return;
            }
            // 保存当前孔洞
            holes.push([...currentHole]);
            currentHole = [];
            updateHolePolygons();
            updateStatsWithHoles();
        }

        function updateModeDisplay() {
            const modeEl = document.getElementById('mode-display');
            if (!modeEl) return;

            if (isDrawMode) {
                modeEl.textContent = '✏️ 绘制外边界';
                modeEl.className = 'mode-badge draw';
            } else if (isHoleMode) {
                modeEl.textContent = '🕳️ 绘制孔洞';
                modeEl.className = 'mode-badge hole';
            } else {
                modeEl.textContent = '👆 选择模式';
                modeEl.className = 'mode-badge idle';
            }
        }

        function addBoundaryPoint(lon, lat) {
            boundaryMarkers.push(new AMap.Marker({
                position: [lon, lat],
                icon: new AMap.Icon({
                    size: new AMap.Size(16, 16),
                    image: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PGNpcmNsZSBjeD0iOCIgY3k9IjgiIHI9IjYiIGZpbGw9IiM2NjdlZWEiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg==',
                    imageOffset: new AMap.Pixel(-8, -8)
                }),
                draggable: true
            }));

            updateBoundaryPolyline();

            // 发送到服务端
            const gpsPoints = boundaryMarkers.map(m => {
                const pos = m.getPosition();
                return [pos.lng, pos.lat];
            });
            socket.emit('update_boundary', {gps_points: gpsPoints});
        }

        function updateBoundaryPolyline() {
            // 清除旧的折线和多边形
            if (boundaryPolyline) {
                boundaryPolyline.setMap(null);
            }
            if (boundaryPolygon) {
                boundaryPolygon.setMap(null);
                boundaryPolygon = null;
            }

            if (boundaryMarkers.length < 2) {
                return;
            }

            const path = boundaryMarkers.map(m => m.getPosition());

            // 绘制折线
            boundaryPolyline = new AMap.Polyline({
                path: path,
                strokeColor: '#667eea',
                strokeWeight: 3,
                strokeOpacity: 0.8
            });
            boundaryPolyline.setMap(map);

            // 绘制多边形（用于填充显示），设置 bubble: false 让点击穿透
            if (boundaryMarkers.length >= 3) {
                boundaryPolygon = new AMap.Polygon({
                    path: path,
                    strokeColor: '#667eea',
                    strokeWeight: 2,
                    strokeOpacity: 0.8,
                    fillColor: '#667eea',
                    fillOpacity: 0.1,
                    bubble: false,  // 关键：不阻止点击事件穿透
                    clickThrough: true  // 允许点击穿透
                });
                boundaryPolygon.setMap(map);
            }
        }

        function addHolePoint(lon, lat) {
            const marker = new AMap.Marker({
                position: [lon, lat],
                icon: new AMap.Icon({
                    size: new AMap.Size(16, 16),
                    image: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PGNpcmNsZSBjeD0iOCIgY3k9IjgiIHI9IjYiIGZpbGw9IiZmZjU3MjIiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg==',
                    imageOffset: new AMap.Pixel(-8, -8)
                }),
                draggable: true
            });
            marker.setMap(map);
            currentHole.push(marker);

            updateCurrentHolePolyline();
        }

        function updateCurrentHolePolyline() {
            // 清除当前孔洞的临时折线
            if (window.currentHolePolyline) {
                window.currentHolePolyline.setMap(null);
            }

            if (currentHole.length < 2) {
                return;
            }

            const path = currentHole.map(m => m.getPosition());

            window.currentHolePolyline = new AMap.Polyline({
                path: path,
                strokeColor: '#ef4444',
                strokeWeight: 2,
                strokeStyle: 'dashed',
                strokeOpacity: 0.8
            });
            window.currentHolePolyline.setMap(map);
        }

        function updateHolePolygons() {
            // 清除所有旧的孔洞多边形
            holePolygons.forEach(p => p.setMap(null));
            holePolygons = [];

            // 绘制所有孔洞
            holes.forEach((hole, index) => {
                if (hole.length < 3) return;

                const path = hole.map(m => m.getPosition());

                // 孔洞折线
                const polyline = new AMap.Polyline({
                    path: path,
                    strokeColor: '#ef4444',
                    strokeWeight: 2,
                    strokeOpacity: 0.8
                });
                polyline.setMap(map);
                holePolygons.push(polyline);

                // 孔洞填充（半透明红色）
                const polygon = new AMap.Polygon({
                    path: path,
                    strokeColor: '#ef4444',
                    strokeWeight: 2,
                    strokeOpacity: 0.8,
                    fillColor: '#ef4444',
                    fillOpacity: 0.2,
                    bubble: false
                });
                polygon.setMap(map);
                holePolygons.push(polygon);
            });
        }

        function undoHolePoint() {
            if (currentHole.length > 0) {
                const marker = currentHole.pop();
                marker.setMap(null);
                updateCurrentHolePolyline();
            } else if (holes.length > 0) {
                // 撤销上一个完成的孔洞
                const lastHole = holes.pop();
                lastHole.forEach(m => m.setMap(null));
                updateHolePolygons();
                updateStatsWithHoles();
            }
        }

        function clearHoles() {
            if (!confirm('确定清除所有孔洞吗？')) return;

            // 清除当前孔洞
            currentHole.forEach(m => m.setMap(null));
            currentHole = [];
            if (window.currentHolePolyline) {
                window.currentHolePolyline.setMap(null);
            }

            // 清除所有已完成的孔洞
            holes.forEach(hole => {
                hole.forEach(m => m.setMap(null));
            });
            holes = [];

            // 清除孔洞多边形
            holePolygons.forEach(p => p.setMap(null));
            holePolygons = [];

            updateStatsWithHoles();
        }

        function updateStatsWithHoles() {
            document.getElementById('stat-holes').textContent = holes.length;
        }

        function updateBoundaryDisplay(boundaryENU) {
            // 更新统计
            document.getElementById('stat-points').textContent = boundaryENU.length;
        }

        function updateStats(data) {
            if (data.area !== undefined) {
                document.getElementById('stat-area').textContent = data.area.toFixed(2) + ' m²';
            }
            if (data.perimeter !== undefined) {
                document.getElementById('stat-perimeter').textContent = data.perimeter.toFixed(2) + ' m';
            }
            if (data.boundary_enu) {
                document.getElementById('stat-points').textContent = data.boundary_enu.length;
            }
        }

        function undoPoint() {
            if (boundaryMarkers.length > 0) {
                const marker = boundaryMarkers.pop();
                marker.setMap(null);
                updateBoundaryPolyline();

                const gpsPoints = boundaryMarkers.map(m => {
                    const pos = m.getPosition();
                    return [pos.lng, pos.lat];
                });
                socket.emit('update_boundary', {gps_points: gpsPoints});
            }
        }

        function clearBoundary() {
            if (!confirm('确定清除绘制的边界吗？')) return;

            // 清除外边界
            boundaryMarkers.forEach(m => m.setMap(null));
            boundaryMarkers = [];
            if (boundaryPolyline) {
                boundaryPolyline.setMap(null);
                boundaryPolyline = null;
            }
            if (boundaryPolygon) {
                boundaryPolygon.setMap(null);
                boundaryPolygon = null;
            }

            // 清除孔洞
            clearHoles();

            socket.emit('clear_boundary');
            document.getElementById('stat-points').textContent = '0';
            document.getElementById('stat-area').textContent = '-- m²';
            document.getElementById('stat-perimeter').textContent = '-- m';
            document.getElementById('stat-holes').textContent = '0';
        }

        function recalcENU() {
            const gpsPoints = boundaryMarkers.map(m => {
                const pos = m.getPosition();
                return [pos.lng, pos.lat];
            });
            socket.emit('update_boundary', {gps_points: gpsPoints, recalc: true});
        }

        function saveParcel() {
            if (!refPoint) {
                alert('请先设置 GPS 参考点');
                return;
            }

            if (boundaryMarkers.length < 3) {
                alert('请至少绘制3个边界点');
                return;
            }

            const name = document.getElementById('parcel-name').value.trim() || 'default';
            const desc = document.getElementById('parcel-desc').value.trim();

            const gpsPoints = boundaryMarkers.map(m => {
                const pos = m.getPosition();
                return [pos.lng, pos.lat];
            });

            // 收集孔洞数据
            const holes_gps = holes.map(hole => {
                return hole.map(m => {
                    const pos = m.getPosition();
                    return [pos.lng, pos.lat];
                });
            });

            const vehicle = {
                implement_width_m: parseFloat(document.getElementById('implement-width').value) || 2.0,
                overlap_ratio: parseFloat(document.getElementById('overlap-ratio').value) || 0.1,
                path_inset_m: parseFloat(document.getElementById('path-inset').value) || 0.5
            };

            socket.emit('save_parcel', {
                name: name,
                description: desc,
                ref_point: refPoint,
                boundary_gps: gpsPoints,
                holes_gps: holes_gps,
                vehicle: vehicle
            });
        }

        socket.on('parcel_saved', function(data) {
            alert('✓ 地块保存成功: ' + data.name);
            currentParcel = data.name;
            document.getElementById('parcel-name').value = data.name;
            refreshParcels();
        });

        function refreshParcels() {
            socket.emit('get_parcels');
        }

        socket.on('parcels_list', function(data) {
            parcels = data.parcels;
            renderParcelList();
        });

        function renderParcelList() {
            const listEl = document.getElementById('parcel-list');

            if (parcels.length === 0) {
                listEl.innerHTML = '<li style="color:#999;font-size:0.9em;">暂无保存的地块</li>';
                return;
            }

            listEl.innerHTML = parcels.map(p => `
                <li class="parcel-item ${p.name === currentParcel ? 'active' : ''}" onclick="loadParcel('${p.name}')">
                    <div class="parcel-name">${p.name}</div>
                    <div class="parcel-desc">${p.description || '无描述'}</div>
                </li>
            `).join('');
        }

        function loadParcel(name) {
            socket.emit('load_parcel', {name: name});
        }

        function loadParcelData(data) {
            clearBoundary();

            document.getElementById('parcel-name').value = data.name || '';
            document.getElementById('parcel-desc').value = data.description || '';

            if (data.ref_point) {
                setRefPoint(data.ref_point.lon, data.ref_point.lat);
            }

            if (data.vehicle) {
                document.getElementById('implement-width').value = data.vehicle.implement_width_m || 2.0;
                document.getElementById('overlap-ratio').value = data.vehicle.overlap_ratio || 0.1;
                document.getElementById('path-inset').value = data.vehicle.path_inset_m || 0.5;
            }

            if (data.boundary_gps && data.boundary_gps.length > 0) {
                data.boundary_gps.forEach(pt => {
                    addBoundaryPoint(pt[0], pt[1]);
                });
                finishDraw();
            }

            // 加载孔洞数据
            if (data.holes_gps && data.holes_gps.length > 0) {
                data.holes_gps.forEach(hole_gps => {
                    const holeMarkers = [];
                    hole_gps.forEach(pt => {
                        const marker = new AMap.Marker({
                            position: [pt[0], pt[1]],
                            icon: new AMap.Icon({
                                size: new AMap.Size(16, 16),
                                image: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PGNpcmNsZSBjeD0iOCIgY3k9IjgiIHI9IjYiIGZpbGw9IiZmZjU3MjIiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg==',
                                imageOffset: new AMap.Pixel(-8, -8)
                            }),
                            draggable: true
                        });
                        marker.setMap(map);
                        holeMarkers.push(marker);
                    });
                    holes.push(holeMarkers);
                });
                updateHolePolygons();
                updateStatsWithHoles();
            }

            if (data.boundary_enu && data.stats) {
                updateStats(data.stats);
            }

            currentParcel = data.name;
            renderParcelList();

            fitView();
        }

        function fitView() {
            if (boundaryMarkers.length === 0) {
                if (refPoint) {
                    map.setCenter([refPoint.lon, refPoint.lat]);
                }
                return;
            }

            const bounds = new AMap.Bounds();
            boundaryMarkers.forEach(m => bounds.extend(m.getPosition()));
            if (refMarker) bounds.extend(refMarker.getPosition());

            map.setFitView(boundaryMarkers.concat(refMarker || []).filter(m => m));
        }
    </script>
</body>
</html>
"""


# ============================================================================
# HTTP 路由
# ============================================================================

@app.route('/')
def index():
    """主页"""
    config = load_config()
    amap_api_key = config.get('amap_api_key', '')

    return render_template_string(HTML_TEMPLATE, amap_api_key=amap_api_key)


@app.route('/api/parcels', methods=['GET'])
def get_parcels():
    """获取已保存的地块列表"""
    parcels = get_parcels_list()
    return jsonify({'parcels': parcels})


@app.route('/api/parcels', methods=['POST'])
def create_parcel():
    """创建/更新地块配置"""
    data = request.json
    name = data.get('name', 'default')

    # 转换边界坐标
    ref_point = data.get('ref_point')
    boundary_gps = data.get('boundary_gps', [])

    boundary_enu = []
    area = 0
    perimeter = 0

    if ref_point and boundary_gps:
        ref_lon = ref_point['lon']
        ref_lat = ref_point['lat']
        boundary_enu = convert_boundary_gps_to_enu(boundary_gps, ref_lon, ref_lat)
        area = calculate_polygon_area(boundary_enu)
        perimeter = calculate_perimeter(boundary_enu)

    # 处理孔洞数据
    holes_gps = data.get('holes_gps', [])
    holes_enu = []
    if ref_point and holes_gps:
        for hole_gps in holes_gps:
            hole_enu = convert_boundary_gps_to_enu(hole_gps, ref_lon, ref_lat)
            holes_enu.append(hole_enu)
            # 减去孔洞面积
            area -= calculate_polygon_area(hole_enu)

    parcel_data = {
        'name': name,
        'description': data.get('description', ''),
        'ref_point': ref_point,
        'boundary_gps': boundary_gps,
        'boundary_enu': boundary_enu,
        'holes_gps': holes_gps,
        'holes_enu': holes_enu,
        'vehicle': data.get('vehicle', {
            'implement_width_m': 2.0,
            'overlap_ratio': 0.1,
            'path_inset_m': 0.5
        }),
        'stats': {
            'area': max(0, area),  # 确保面积非负
            'perimeter': perimeter,
            'points': len(boundary_gps),
            'holes': len(holes_gps)
        }
    }

    if save_parcel_data(name, parcel_data):
        return jsonify({'success': True, 'name': name})
    return jsonify({'success': False, 'error': 'Save failed'}), 500


@app.route('/api/parcels/<name>', methods=['GET'])
def get_parcel(name):
    """获取指定地块"""
    data = load_parcel_data(name)
    if data:
        return jsonify(data)
    return jsonify({'error': 'Parcel not found'}), 404


@app.route('/api/parcels/<name>', methods=['DELETE'])
def delete_parcel(name):
    """删除地块"""
    if delete_parcel_data(name):
        return jsonify({'success': True, 'name': name})
    return jsonify({'success': False, 'error': 'Delete failed'}), 404


@app.route('/api/convert', methods=['POST'])
def convert_coordinates():
    """坐标转换接口"""
    data = request.json
    mode = data.get('mode', 'gps_to_enu')

    if mode == 'gps_to_enu':
        result = gps_to_enu(
            data['lon'], data['lat'],
            data['ref_lon'], data['ref_lat']
        )
        return jsonify({'x': result[0], 'y': result[1]})
    else:
        result = enu_to_gps(
            data['x'], data['y'],
            data['ref_lon'], data['ref_lat']
        )
        return jsonify({'lon': result[0], 'lat': result[1]})


# ============================================================================
# WebSocket 事件处理
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f"[WebSocket] 客户端已连接")

    # 发送当前状态
    emit('parcel_update', {
        'ref_point': current_state['ref_point'],
        'boundary_enu': current_state['boundary_enu'],
        'parcels': get_parcels_list()
    })


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print(f"[WebSocket] 客户端已断开")


@socketio.on('set_ref_point')
def handle_set_ref_point(data):
    """设置 GPS 参考点"""
    current_state['ref_point'] = {
        'lon': data['lon'],
        'lat': data['lat']
    }
    emit('parcel_update', {'ref_point': current_state['ref_point']}, broadcast=True)


@socketio.on('update_boundary')
def handle_update_boundary(data):
    """更新边界"""
    ref_point = current_state.get('ref_point')
    gps_points = data.get('gps_points', [])

    if ref_point and gps_points:
        boundary_enu = convert_boundary_gps_to_enu(
            gps_points,
            ref_point['lon'],
            ref_point['lat']
        )
        current_state['boundary_gps'] = gps_points
        current_state['boundary_enu'] = boundary_enu

        # 计算统计信息
        area = calculate_polygon_area(boundary_enu)
        perimeter = calculate_perimeter(boundary_enu)

        emit('parcel_update', {
            'boundary_enu': boundary_enu,
            'area': area,
            'perimeter': perimeter
        }, broadcast=True)


@socketio.on('clear_boundary')
def handle_clear_boundary():
    """清除边界"""
    current_state['boundary_gps'] = []
    current_state['boundary_enu'] = []
    emit('parcel_update', {
        'boundary_enu': [],
        'area': 0,
        'perimeter': 0
    }, broadcast=True)


@socketio.on('save_parcel')
def handle_save_parcel(data):
    """保存地块"""
    name = data.get('name', 'default')

    # 转换边界坐标
    ref_point = data.get('ref_point')
    boundary_gps = data.get('boundary_gps', [])
    holes_gps = data.get('holes_gps', [])

    boundary_enu = []
    holes_enu = []
    area = 0
    perimeter = 0

    if ref_point and boundary_gps:
        ref_lon = ref_point['lon']
        ref_lat = ref_point['lat']
        boundary_enu = convert_boundary_gps_to_enu(boundary_gps, ref_lon, ref_lat)
        area = calculate_polygon_area(boundary_enu)
        perimeter = calculate_perimeter(boundary_enu)

    # 处理孔洞
    if ref_point and holes_gps:
        for hole_gps in holes_gps:
            hole_enu = convert_boundary_gps_to_enu(hole_gps, ref_lon, ref_lat)
            holes_enu.append(hole_enu)
            area -= calculate_polygon_area(hole_enu)

    parcel_data = {
        'name': name,
        'description': data.get('description', ''),
        'ref_point': ref_point,
        'boundary_gps': boundary_gps,
        'boundary_enu': boundary_enu,
        'holes_gps': holes_gps,
        'holes_enu': holes_enu,
        'vehicle': data.get('vehicle', {
            'implement_width_m': 2.0,
            'overlap_ratio': 0.1,
            'path_inset_m': 0.5
        }),
        'stats': {
            'area': max(0, area),
            'perimeter': perimeter,
            'points': len(boundary_gps),
            'holes': len(holes_gps)
        }
    }

    if save_parcel_data(name, parcel_data):
        current_state['current_parcel'] = name
        emit('parcel_saved', {'name': name}, broadcast=True)
        emit('parcel_update', {'parcels': get_parcels_list()}, broadcast=True)
    else:
        emit('error', {'message': 'Save failed'})


@socketio.on('get_parcels')
def handle_get_parcels():
    """获取地块列表"""
    emit('parcels_list', {'parcels': get_parcels_list()})


@socketio.on('load_parcel')
def handle_load_parcel(data):
    """加载地块"""
    name = data.get('name')
    parcel_data = load_parcel_data(name)

    if parcel_data:
        current_state['ref_point'] = parcel_data.get('ref_point')
        current_state['boundary_gps'] = parcel_data.get('boundary_gps', [])
        current_state['boundary_enu'] = parcel_data.get('boundary_enu', [])
        current_state['current_parcel'] = name

        emit('parcel_loaded', parcel_data)
    else:
        emit('error', {'message': 'Parcel not found'})


@socketio.on('convert_to_enu')
def handle_convert_to_enu(data):
    """转换 GPS 到 ENU（实时显示用）"""
    ref_point = current_state.get('ref_point')
    if not ref_point:
        return

    x, y = gps_to_enu(
        data['lon'], data['lat'],
        ref_point['lon'], ref_point['lat']
    )
    emit('enu_result', {'x': x, 'y': y})


# ============================================================================
# 服务器启动
# ============================================================================

def start_web_server(host='0.0.0.0', port=8081):
    """
    启动 Web 服务器（在单独的线程中）

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        服务器线程对象
    """
    def run_server():
        print(f"🌐 地块规划服务器启动:")
        print(f"   地址: http://{host}:{port}")
        print(f"   请在浏览器中打开此地址进行地块规划")
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread


def stop_web_server():
    """停止 Web 服务器（优雅关闭）"""
    print("🔴 正在关闭 Web 服务器...")
    socketio.stop()
    print("✅ Web 服务器已关闭")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='地块规划 Web 服务器')
    parser.add_argument('--host', help='监听地址')
    parser.add_argument('--port', type=int, help='监听端口')
    parser.add_argument('--api-key', help='高德地图 API Key')
    args = parser.parse_args()

    # 加载配置
    config = load_config()

    # 命令行参数优先级最高
    host = args.host or config.get('web_host', '0.0.0.0')
    port = args.port or config.get('web_port', 8081)
    api_key = args.api_key or config.get('amap_api_key', '')

    if api_key:
        os.environ['AMAP_API_KEY'] = api_key

    print("=" * 60)
    print("🌐 地块规划 Web 服务器")
    print(f"   地址: http://{host}:{port}")
    print(f"   API Key: {'已设置' if api_key else '未设置'}")
    if not api_key:
        print(f"   警告: 请在 config.json 中设置 amap_api_key")
    print("=" * 60)

    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
