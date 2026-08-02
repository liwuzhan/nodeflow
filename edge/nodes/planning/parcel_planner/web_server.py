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
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from typing import Dict, Any, Optional, List

# 导入坐标转换算法
try:
    from .atom import gps_to_enu, enu_to_gps, convert_boundary_gps_to_enu, convert_boundary_enu_to_gps, calculate_polygon_area, calculate_perimeter
except ImportError:  # Direct script execution from the node directory.
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
        'amap_security_code': '',
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
    if os.environ.get('AMAP_SECURITY_CODE'):
        config['amap_security_code'] = os.environ.get('AMAP_SECURITY_CODE')

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


# ============================================================================
# HTTP 路由
# ============================================================================

@app.route('/')
def index():
    """主页"""
    config = load_config()
    amap_api_key = config.get('amap_api_key', '')
    amap_security_code = config.get('amap_security_code', '')
    return render_template('index.html', amap_api_key=amap_api_key, amap_security_code=amap_security_code)


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


@socketio.on('delete_parcel')
def handle_delete_parcel(data):
    """删除地块"""
    name = data.get('name')
    if not name:
        emit('error', {'message': '地块名称不能为空'})
        return

    if delete_parcel_data(name):
        # 如果删除的是当前地块，清除状态
        if current_state.get('current_parcel') == name:
            current_state['current_parcel'] = None

        emit('parcel_deleted', {'name': name}, broadcast=True)
        emit('parcel_update', {'parcels': get_parcels_list()}, broadcast=True)
        print(f"[WebSocket] 已删除地块: {name}")
    else:
        emit('error', {'message': f'删除地块失败: {name}'})


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
