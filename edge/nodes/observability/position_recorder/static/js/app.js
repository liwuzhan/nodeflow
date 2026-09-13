// 位置记录工具 - 前端逻辑

// Socket 连接
let socket = null;

// 状态
let currentStatus = {
    is_recording: false,
    point_count: 0,
    current_rtk: null,
    record_start_time: null,
    elapsed_seconds: 0,
    auto_record_enabled: false
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initSocket();
    updateUI();
    setInterval(updateElapsedTime, 1000);
});

// 初始化 Socket 连接
function initSocket() {
    socket = io();

    socket.on('connect', function() {
        updateConnectionStatus('connected');
        console.log('[Socket] 已连接');
    });

    socket.on('disconnect', function() {
        updateConnectionStatus('disconnected');
        console.log('[Socket] 已断开');
    });

    socket.on('connected', function(data) {
        console.log('[Socket]', data.message);
        // 请求初始状态
        socket.emit('get_status');
        refreshRecords();
    });

    socket.on('status_update', function(status) {
        currentStatus = status;
        updateUI();
    });

    socket.on('recording_started', function(result) {
        if (result.success) {
            console.log('[记录] 已开始');
        } else {
            alert('开始记录失败: ' + (result.error || '未知错误'));
        }
    });

    socket.on('recording_stopped', function(result) {
        if (result.success) {
            alert(`记录已保存: ${result.filename}\n点数: ${result.point_count}`);
            refreshRecords();
        } else {
            alert('停止记录失败: ' + (result.error || '未知错误'));
        }
    });

    socket.on('auto_record_toggled', function(data) {
        console.log('[自动记录]', data.enabled ? '已启用' : '已禁用');
    });

    socket.on('records_list', function(data) {
        renderRecordsList(data.records);
    });
}

// 更新连接状态
function updateConnectionStatus(status) {
    const el = document.getElementById('connection-status');
    el.className = status === 'connected' ? 'connected' : 'disconnected';
    el.textContent = status === 'connected' ? '● 已连接' : '○ 已断开';
}

// 更新界面
function updateUI() {
    // RTK 数据
    updateRTKDisplay();

    // 记录状态
    updateRecordingStatus();

    // 按钮状态
    updateButtons();
}

// 更新 RTK 显示
function updateRTKDisplay() {
    const rtk = currentStatus.current_rtk;

    if (rtk) {
        document.getElementById('rtk-status').textContent = rtk.rtk_status || '--';
        document.getElementById('rtk-lat').textContent = rtk.lat?.toFixed(8) || '--';
        document.getElementById('rtk-lon').textContent = rtk.lon?.toFixed(8) || '--';
        document.getElementById('rtk-alt').textContent = rtk.alt?.toFixed(2) + ' m' || '--';
        document.getElementById('rtk-heading').textContent = rtk.heading?.toFixed(1) + '°' || '--';
        document.getElementById('rtk-sats').textContent = rtk.num_satellites || '--';
    } else {
        document.getElementById('rtk-status').textContent = '--';
        document.getElementById('rtk-lat').textContent = '--';
        document.getElementById('rtk-lon').textContent = '--';
        document.getElementById('rtk-alt').textContent = '--';
        document.getElementById('rtk-heading').textContent = '--';
        document.getElementById('rtk-sats').textContent = '--';
    }

    // 点数
    document.getElementById('point-count').textContent = currentStatus.point_count;
}

// 更新记录状态
function updateRecordingStatus() {
    const indicator = document.getElementById('recording-indicator');

    if (currentStatus.is_recording) {
        indicator.className = 'recording-badge active';
        indicator.textContent = '● 记录中';
    } else {
        indicator.className = 'recording-badge idle';
        indicator.textContent = '● 未记录';
    }

    // 自动记录状态
    document.getElementById('auto-record-status').textContent =
        currentStatus.auto_record_enabled ? '已启用' : '已禁用';
}

// 更新按钮状态
function updateButtons() {
    const hasRTK = currentStatus.current_rtk != null;
    const isRecording = currentStatus.is_recording;

    document.getElementById('btn-start').disabled = isRecording;
    document.getElementById('btn-stop').disabled = !isRecording;
    document.getElementById('btn-add-point').disabled = !hasRTK || !isRecording;
    document.getElementById('btn-clear').disabled = currentStatus.point_count === 0;
}

// 更新经过时间
function updateElapsedTime() {
    if (currentStatus.is_recording && currentStatus.record_start_time) {
        const elapsed = Math.floor(Date.now() / 1000) - currentStatus.record_start_time;
        const minutes = Math.floor(elapsed / 60);
        const seconds = elapsed % 60;
        document.getElementById('elapsed-time').textContent =
            minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
    } else {
        document.getElementById('elapsed-time').textContent = '0s';
    }
}

// 开始记录
function startRecording() {
    socket.emit('start_recording');
}

// 停止记录
function stopRecording() {
    socket.emit('stop_recording');
}

// 添加点
function addPoint() {
    socket.emit('add_point');
}

// 切换自动记录
function toggleAutoRecord() {
    const enabled = document.getElementById('auto-record-toggle').checked;
    socket.emit('toggle_auto_record', { enabled: enabled });
}

// 清空点
function clearPoints() {
    if (confirm('确定要清空所有记录点吗？')) {
        socket.emit('clear_points');
    }
}

// 刷新记录列表
function refreshRecords() {
    socket.emit('refresh_records');
}

// 渲染记录列表
function renderRecordsList(records) {
    const listEl = document.getElementById('record-list');

    if (!records || records.length === 0) {
        listEl.innerHTML = '<li class="empty">暂无保存的记录</li>';
        return;
    }

    listEl.innerHTML = records.map(record => `
        <li>
            <div class="record-info">
                <div class="record-name">${record.name}</div>
                <div class="record-meta">${formatFileSize(record.size)} · ${record.modified_iso}</div>
            </div>
            <div class="record-actions">
                <button class="btn-primary" onclick="downloadRecord('${record.name}')">⬇</button>
                <button class="btn-danger" onclick="deleteRecord('${record.name}')">🗑</button>
            </div>
        </li>
    `).join('');
}

// 下载记录
function downloadRecord(filename) {
    window.location.href = `/api/records/download/${filename}`;
}

// 删除记录
function deleteRecord(filename) {
    if (confirm(`确定要删除记录 "${filename}" 吗？`)) {
        fetch(`/api/records/delete/${filename}`, {
            method: 'DELETE'
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                refreshRecords();
            } else {
                alert('删除失败: ' + (data.error || '未知错误'));
            }
        })
        .catch(err => {
            alert('删除失败: ' + err.message);
        });
    }
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}
