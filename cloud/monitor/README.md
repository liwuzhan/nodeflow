# NodeFlow Monitor

监工界面 —— 全屏地图，实时显示车辆位置、作业进度。

与 `cloud/web/`（农场管理后台）的区别：
- Monitor 是**只读监工台**，看机器干活
- Web 是**管理后台**，创建作业、配置地块、分配车辆

## 运行

```bash
cd cloud/monitor
npm install
npm run dev        # 开发模式，localhost:3000
npm run build      # 生产构建 → dist/
```

后端需要先启动：
```bash
cd cloud/server
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Vite 开发代理将 `/api` 转发到 `localhost:8000`。

## 架构

```
App.vue
├── MonitorMap.vue     # 全屏 Leaflet 地图
│   ├── 地块 GeoJSON（按进度着色）
│   └── 车辆 CircleMarker（实时位置）
├── MachinePanel.vue   # 左上角浮动车辆列表
└── StatusBar.vue      # 底部 SSE 连接状态
```

数据流：SSE（heartbeat/task_status）→ monitorStore → 地图/面板更新。
