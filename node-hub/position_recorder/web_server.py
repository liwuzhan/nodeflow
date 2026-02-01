#!/usr/bin/env python3
"""
位置记录 Web 服务器

提供 Flask + SocketIO Web服务器接口
职责：纯粹的Web服务，业务逻辑回调到节点主程序
"""

import os
from pathlib import Path
from flask import Flask, render_template, send_file, jsonify, request
from flask_socketio import SocketIO, emit

# Flask 应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'position-recorder-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 节点回调（由run.py设置）
_node_callback = None
_auto_record_enabled = False


def set_record_callback(node):
    """设置节点回调对象"""
    global _node_callback
    _node_callback = node


# ============================================================================
# HTTP 路由
# ============================================================================

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def get_status():
    """获取当前状态"""
    if _node_callback:
        status = _node_callback.get_current_status()
        status['auto_record_enabled'] = _auto_record_enabled
        return jsonify(status)
    return jsonify({'error': 'Node not ready'}), 503


@app.route('/api/records', methods=['GET'])
def get_records():
    """获取已保存的记录列表"""
    if _node_callback:
        records = _node_callback.get_records_list()
        return jsonify({'records': records})
    return jsonify({'error': 'Node not ready'}), 503


@app.route('/api/records/download/<filename>', methods=['GET'])
def download_record(filename):
    """下载记录文件"""
    records_dir = Path(__file__).parent / 'data' / 'records'
    filepath = records_dir / filename

    if filepath.exists() and filepath.is_file():
        return send_file(str(filepath), as_attachment=True, download_name=filename)
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/records/delete/<filename>', methods=['DELETE'])
def delete_record(filename):
    """删除记录文件"""
    records_dir = Path(__file__).parent / 'data' / 'records'
    filepath = records_dir / filename

    try:
        if filepath.exists() and filepath.is_file():
            os.remove(filepath)
            return jsonify({'success': True, 'filename': filename})
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# WebSocket 事件处理
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f"[WebSocket] 客户端已连接")
    emit('connected', {'message': '已连接到位置记录服务器'})


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print(f"[WebSocket] 客户端已断开")


@socketio.on('get_status')
def handle_get_status():
    """获取状态"""
    if _node_callback:
        status = _node_callback.get_current_status()
        status['auto_record_enabled'] = _auto_record_enabled
        emit('status_update', status)


@socketio.on('start_recording')
def handle_start_recording():
    """开始记录"""
    if _node_callback:
        result = _node_callback.start_recording()
        emit('recording_started', result)
        return result
    return {'success': False, 'error': 'Node not ready'}


@socketio.on('stop_recording')
def handle_stop_recording():
    """停止记录"""
    if _node_callback:
        result = _node_callback.stop_recording()
        emit('recording_stopped', result)

        # 广播状态更新
        status = _node_callback.get_current_status()
        status['auto_record_enabled'] = _auto_record_enabled
        emit('status_update', status, broadcast=True)

        return result
    return {'success': False, 'error': 'Node not ready'}


@socketio.on('add_point')
def handle_add_point():
    """手动添加点"""
    if _node_callback:
        result = _node_callback.add_point()

        # 广播状态更新
        status = _node_callback.get_current_status()
        status['auto_record_enabled'] = _auto_record_enabled
        emit('status_update', status, broadcast=True)

        return result
    return {'success': False, 'error': 'Node not ready'}


@socketio.on('toggle_auto_record')
def handle_toggle_auto_record(data):
    """切换自动记录"""
    global _auto_record_enabled
    enabled = data.get('enabled', False)
    _auto_record_enabled = enabled

    if _node_callback:
        result = _node_callback.toggle_auto_record(enabled)
        emit('auto_record_toggled', {'enabled': enabled})
        return result
    return {'success': False, 'error': 'Node not ready'}


@socketio.on('clear_points')
def handle_clear_points():
    """清除记录点"""
    if _node_callback:
        result = _node_callback.clear_points()

        # 广播状态更新
        status = _node_callback.get_current_status()
        status['auto_record_enabled'] = _auto_record_enabled
        emit('status_update', status, broadcast=True)

        return result
    return {'success': False, 'error': 'Node not ready'}


@socketio.on('refresh_records')
def handle_refresh_records():
    """刷新记录列表"""
    if _node_callback:
        records = _node_callback.get_records_list()
        emit('records_list', {'records': records})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='位置记录 Web 服务器')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=8082, help='监听端口')
    args = parser.parse_args()

    print("=" * 60)
    print("🌐 位置记录 Web 服务器")
    print(f"   地址: http://{args.host}:{args.port}")
    print("=" * 60)

    socketio.run(app, host=args.host, port=args.port, debug=False, allow_unsafe_werkzeug=True)
