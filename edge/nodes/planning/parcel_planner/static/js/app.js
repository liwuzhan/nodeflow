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
        const AMAP_API_KEY = window.AMAP_API_KEY || '';

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
                // 显示删除成功提示
                const statusEl = document.getElementById('connection-status');
                statusEl.textContent = `🗑️ 已删除: ${data.name}`;
                setTimeout(() => {
                    statusEl.textContent = '✅ 已连接';
                }, 2000);

                // 如果删除的是当前地块，清除编辑器
                if (data.name === currentParcel) {
                    currentParcel = null;
                }

                // 刷新地块列表
                refreshParcels();
            });

            socket.on('enu_result', function(data) {
                document.getElementById('cursor-enu').textContent =
                    `${data.x.toFixed(2)}, ${data.y.toFixed(2)}m`;
            });

            socket.on('parcel_saved', function(data) {
                alert('✓ 地块保存成功: ' + data.name);
                currentParcel = data.name;
                document.getElementById('parcel-name').value = data.name;
                refreshParcels();
            });

            socket.on('parcels_list', function(data) {
                parcels = data.parcels;
                renderParcelList();
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

            // 如果有孔洞在绘制中，先清空
            if (currentHole.length > 0) {
                currentHole.forEach(m => m.setMap(null));
                currentHole = [];
                if (window.currentHolePolyline) {
                    window.currentHolePolyline.setMap(null);
                }
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

            // 清除当前未完成的孔洞（如果有）
            if (currentHole.length > 0) {
                if (!confirm('当前有未完成的孔洞点，是否清除？')) {
                    return;
                }
                currentHole.forEach(m => m.setMap(null));
                currentHole = [];
                if (window.currentHolePolyline) {
                    window.currentHolePolyline.setMap(null);
                }
            }

            isHoleMode = true;
            isDrawMode = false;
            currentHole = [];
            document.body.style.cursor = 'crosshair';
            updateModeDisplay();

            alert('🕳️ 进入孔洞绘制模式\n\n在地图上点击添加孔洞边界点\n点击"完成孔洞"保存当前孔洞\n点击"完成当前"退出孔洞模式');
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

            // 保持孔洞模式，可以继续绘制下一个孔洞
            // 提示用户可以继续绘制或退出
            alert(`✓ 孔洞已保存！当前共 ${holes.length} 个孔洞。\n\n点击"完成当前"退出孔洞模式。`);
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
            const marker = new AMap.Marker({
                position: [lon, lat],
                icon: new AMap.Icon({
                    size: new AMap.Size(16, 16),
                    image: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PGNpcmNsZSBjeD0iOCIgY3k9IjgiIHI9IjYiIGZpbGw9IiM2NjdlZWEiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg==',
                    imageOffset: new AMap.Pixel(-8, -8)
                }),
                draggable: true
            });
            marker.setMap(map);  // 关键：将标记添加到地图上
            boundaryMarkers.push(marker);

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

            // 绘制多边形（用于填充显示）
            // 关键：设置 draggable: false 和 bubble: false，并监听点击事件转发给地图
            if (boundaryMarkers.length >= 3) {
                boundaryPolygon = new AMap.Polygon({
                    path: path,
                    strokeColor: '#667eea',
                    strokeWeight: 2,
                    strokeOpacity: 0.8,
                    fillColor: '#667eea',
                    fillOpacity: 0.1,
                    bubble: false  // 不冒泡事件到其他覆盖物
                });

                // 监听多边形点击，将点击转发给地图
                boundaryPolygon.on('click', function(e) {
                    const lnglat = e.lnglat;
                    // 手动触发地图点击逻辑
                    updateCursorDisplay(lnglat.lng, lnglat.lat);

                    if (isPickRefMode) {
                        setRefPoint(lnglat.lng, lnglat.lat);
                        isPickRefMode = false;
                        document.body.style.cursor = 'default';
                    } else if (isHoleMode && refPoint) {
                        addHolePoint(lnglat.lng, lnglat.lat);
                    } else if (isDrawMode && refPoint) {
                        addBoundaryPoint(lnglat.lng, lnglat.lat);
                    }
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

                // 监听孔洞多边形点击，将点击转发给地图
                polygon.on('click', function(e) {
                    const lnglat = e.lnglat;
                    updateCursorDisplay(lnglat.lng, lnglat.lat);

                    if (isHoleMode && refPoint) {
                        addHolePoint(lnglat.lng, lnglat.lat);
                    } else if (isDrawMode && refPoint) {
                        addBoundaryPoint(lnglat.lng, lnglat.lat);
                    }
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

        function refreshParcels() {
            socket.emit('get_parcels');
        }

        function renderParcelList() {
            const listEl = document.getElementById('parcel-list');

            if (parcels.length === 0) {
                listEl.innerHTML = '<li style="color:#999;font-size:0.9em;">暂无保存的地块</li>';
                return;
            }

            listEl.innerHTML = parcels.map(p => {
                // 格式化更新时间
                let timeStr = '';
                if (p.updated_at) {
                    try {
                        const date = new Date(p.updated_at);
                        timeStr = date.toLocaleString('zh-CN', {
                            month: 'numeric',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    } catch(e) {
                        timeStr = '';
                    }
                }

                return `
                <li class="parcel-item ${p.name === currentParcel ? 'active' : ''}">
                    <div class="parcel-item-content" onclick="loadParcel('${p.name}')">
                        <div class="parcel-name">${p.name}</div>
                        <div class="parcel-desc">${p.description || '无描述'}</div>
                        ${timeStr ? `<div class="parcel-time">🕐 ${timeStr}</div>` : ''}
                    </div>
                    <div class="parcel-actions">
                        <button class="btn-icon btn-view" onclick="event.stopPropagation(); loadParcel('${p.name}')" title="查看地块">👁️</button>
                        <button class="btn-icon btn-delete" onclick="event.stopPropagation(); deleteParcel('${p.name}')" title="删除地块">🗑️</button>
                    </div>
                </li>
            `}).join('');
        }

        function deleteParcel(name) {
            if (!confirm(`确定要删除地块 "${name}" 吗？\n此操作不可恢复！`)) {
                return;
            }

            socket.emit('delete_parcel', {name: name});

            // 如果删除的是当前地块，清除编辑器
            if (name === currentParcel) {
                clearBoundary();
                currentParcel = null;
                document.getElementById('parcel-name').value = 'default';
                document.getElementById('parcel-desc').value = '';
            }
        }

        function loadParcel(name) {
            // 显示加载提示
            const statusEl = document.getElementById('connection-status');
            const oldStatus = statusEl.textContent;
            statusEl.textContent = `📥 加载地块: ${name}...`;

            socket.emit('load_parcel', {name: name});

            // 2秒后恢复状态显示
            setTimeout(() => {
                if (statusEl.textContent.includes('加载地块')) {
                    statusEl.textContent = oldStatus;
                }
            }, 2000);
        }

        function loadParcelData(data) {
            // 先清除旧数据
            clearBoundary();

            // 更新地块信息
            document.getElementById('parcel-name').value = data.name || '';
            document.getElementById('parcel-desc').value = data.description || '';

            // 1. 首先设置参考点并将地图中心移动到参考点
            if (data.ref_point) {
                const refLon = data.ref_point.lon;
                const refLat = data.ref_point.lat;

                // 先移动地图中心到参考点，设置合适的缩放级别
                map.setZoomAndCenter(16, [refLon, refLat]);

                // 然后设置参考点标记
                setRefPoint(refLon, refLat);
            }

            // 2. 更新车辆配置
            if (data.vehicle) {
                document.getElementById('implement-width').value = data.vehicle.implement_width_m || 2.0;
                document.getElementById('overlap-ratio').value = data.vehicle.overlap_ratio || 0.1;
                document.getElementById('path-inset').value = data.vehicle.path_inset_m || 0.5;
            }

            // 3. 绘制外边界
            if (data.boundary_gps && data.boundary_gps.length > 0) {
                data.boundary_gps.forEach(pt => {
                    addBoundaryPoint(pt[0], pt[1]);
                });
                finishDraw();
            }

            // 4. 绘制孔洞
            if (data.holes_gps && data.holes_gps.length > 0) {
                data.holes_gps.forEach(hole_gps => {
                    const holeMarkers = [];
                    hole_gps.forEach(pt => {
                        const marker = new AMap.Marker({
                            position: [pt[0], pt[1]],
                            icon: new AMap.Icon({
                                size: new AMap.Size(16, 16),
                                image: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PGNpcmNsZSBjeD0iOCIgY3k9IjgiIHI9IjYiIGZpbGw9IiNmZjU3MjIiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIvPjwvc3ZnPg==',
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

            // 5. 更新统计信息
            if (data.boundary_enu && data.stats) {
                updateStats(data.stats);
            }

            // 6. 更新当前地块状态
            currentParcel = data.name;
            renderParcelList();

            // 7. 延迟调整视图，确保所有标记已添加到地图
            setTimeout(() => {
                fitView();
            }, 100);

            // 8. 显示加载成功提示
            const statusEl = document.getElementById('connection-status');
            statusEl.textContent = `✅ 已加载: ${data.name}`;
            setTimeout(() => {
                statusEl.textContent = '✅ 已连接';
            }, 3000);
        }

        function fitView() {
            if (boundaryMarkers.length === 0) {
                // 如果没有边界点，只跳转到参考点并设置合适的缩放
                if (refPoint) {
                    map.setZoomAndCenter(16, [refPoint.lon, refPoint.lat]);
                }
                return;
            }

            // 收集所有需要显示的覆盖物
            const overlays = [...boundaryMarkers];

            // 添加参考点标记
            if (refMarker) {
                overlays.push(refMarker);
            }

            // 添加孔洞点
            holes.forEach(hole => {
                overlays.push(...hole);
            });

            // 使用高德地图的 setFitView 自动调整视图
            // 参数: overlays, immediately, avoid(边距), maxZoom
            map.setFitView(overlays, false, [50, 50, 50, 50], 18);
        }
