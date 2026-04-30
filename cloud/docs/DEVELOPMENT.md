# NodeFlow Cloud 农场管理平台 — 开发手册

> 最后更新: 2026-04-30

## 1. 系统架构

```
┌── 云端 (cloud/server + cloud/web) ──────────────────────┐
│                                                           │
│  FarmMapView  MachineDashboard  JobCreateView  ...        │
│       │              │               │                    │
│  Pinia Stores  ←→  Services (REST + SSE)                 │
│       │                                                  │
│  FastAPI (25 端点) ── MQTT Client ── Splitter ── SQLite  │
│       │              (paho-mqtt)    (shapely)            │
└───────┼──────────────────────────────────────────────────┘
        │ MQTT (QoS 1 control / QoS 0 status + heartbeat)
┌───────┼──────────────────────────────────────────────────┐
│  Edge Side (runtime/task/)                               │
│       │                                                  │
│  TaskAgent ── TaskExecutor ── Runtime Daemon             │
│  (MQTT Sub)  (control buffer)  (注入 node_params → 节点) │
└──────────────────────────────────────────────────────────┘
```

**三层网络模型**:
1. **前端 ←→ 后端**: HTTP REST + SSE 推送
2. **云端 ←→ 边侧**: MQTT (任务下发 QoS 1, 状态/心跳 QoS 0)
3. **云端 → 边侧**: HTTP 大文件下载 (地块/路径 > 1MB)

---

## 2. 目录结构

```
cloud/
├── server/                          # 后端 (Python/FastAPI)
│   ├── app.py                       # FastAPI 入口, lifespan (MQTT 启停)
│   ├── config.py                    # Settings (DB URL, MQTT broker, ...)
│   ├── database.py                  # SQLAlchemy engine + Session
│   ├── requirements.txt
│   ├── models/                      # SQLAlchemy ORM 模型
│   │   ├── parcel.py                # Parcel, ParcelSplit
│   │   ├── machine.py               # Machine
│   │   ├── job.py                   # Job, JobStep
│   │   └── edge_task.py             # EdgeTask (下发追踪)
│   ├── schemas/                     # Pydantic 请求/响应模型
│   │   ├── parcel.py, machine.py, job.py, edge_task.py
│   ├── routers/                     # API 路由 (25 端点)
│   │   ├── parcels.py               # 地块 CRUD + 分割预览
│   │   ├── machines.py              # 机器 CRUD + 确认注册
│   │   ├── jobs.py                  # 作业 CRUD + 下发 + 取消
│   │   ├── tasks.py                 # EdgeTask 追踪 + 重试
│   │   ├── files.py                 # 大文件下载 (GeoJSON + MsgPack)
│   │   └── events.py                # SSE 推送
│   ├── services/                    # 业务逻辑
│   │   ├── mqtt_client.py           # MQTT 连接 + 心跳/状态/ACK 处理
│   │   ├── dispatcher.py            # 任务下发引擎 (payload构建 + ACK重试)
│   │   ├── splitter.py              # 地块分割算法 (strip/checkerboard)
│   │   ├── heartbeat_monitor.py     # 心跳超时 → 标记离线
│   │   └── sse_broker.py            # 进程内事件扇出 → SSE
│   └── tests/                       # 5 个测试
├── web/                             # 前端 (Vue 3 + TS + Vite)
│   ├── package.json, vite.config.ts, tsconfig.json, index.html
│   └── src/
│       ├── App.vue, main.ts
│       ├── router/index.ts          # 6 个路由
│       ├── views/                   # 6 个页面
│       │   ├── FarmMapView.vue      # 主地图 + 地块 + 手绘
│       │   ├── MachineDashboard.vue # 机器监控 + 自动发现确认
│       │   ├── JobListView.vue      # 作业历史
│       │   ├── JobCreateView.vue    # 3步向导
│       │   ├── JobDetailView.vue    # 时间线 + 进度
│       │   └── SettingsView.vue     # MQTT 配置 + 注册机器
│       ├── components/
│       │   ├── layout/              # CloudLayout, SideNav, TopBar
│       │   ├── map/                 # FarmMap, ParcelLayer, SplitPreview, ParcelDrawer, MachineMarker
│       │   ├── job/                 # JobTimeline
│       │   ├── machine/             # MachineCard, MachineGrid
│       │   └── common/              # StatusBadge, EmptyState
│       ├── stores/                  # parcel, machine, job, map, ui (Pinia)
│       ├── services/                # api, parcelApi, machineApi, jobApi, statusStream
│       ├── models/                  # TypeScript 接口
│       └── utils/                   # formatters, geo
├── docs/
│   ├── CLOUD_INTEGRATION.md         # 端侧对接协议规范
│   └── DEVELOPMENT.md               # 本文件
└── README.md                        # 云端部署说明 (待补充)
```

---

## 3. 数据模型

### 6 张表

| 表 | 主键 | 关键字段 | 说明 |
|---|---|---|---|
| `parcels` | UUID | name, geojson, area_ha, vehicle_cfg, ref_point | 地块 |
| `parcel_splits` | UUID | parcel_id(FK), job_id, index, geojson, assigned_to | 子地块 |
| `machines` | String | name, type, status, last_heartbeat, current_task_id | 机器 |
| `jobs` | String | name, parcel_id, status, split_mode, split_count | 作业 |
| `job_steps` | UUID | job_id(FK), seq_index, operation_type, preset_yaml, depends_on | 作业步骤 |
| `edge_tasks` | UUID | edge_task_id(UNIQUE), machine_id, dispatch_id, state, progress_pct | 下发追踪 |

### 状态机

**Machine**: `unregistered` → (操作员确认) → `online` / `offline` → `busy` → `online`

**Job**: `draft` → `ready` → `running` → `completed` / `failed` / `cancelled`

**EdgeTask**: `pending` → `downloading` → `ready` → `running` → `completed` / `failed`

---

## 4. API 端点 (25 个)

```
地块:
  GET    /api/v1/parcels                         列表
  POST   /api/v1/parcels                         创建 (GeoJSON body)
  GET    /api/v1/parcels/{id}                    详情
  PUT    /api/v1/parcels/{id}                    更新
  DELETE /api/v1/parcels/{id}                    删除
  POST   /api/v1/parcels/{id}/preview-split      分割预览
  GET    /api/v1/parcels/{id}/geojson            端侧下载

机器:
  GET    /api/v1/machines                        列表
  POST   /api/v1/machines                        注册
  GET    /api/v1/machines/{id}                   详情
  PUT    /api/v1/machines/{id}                   更新
  POST   /api/v1/machines/{id}/confirm           确认自动发现
  DELETE /api/v1/machines/{id}                   删除

作业:
  GET    /api/v1/jobs                            列表
  POST   /api/v1/jobs                            创建
  GET    /api/v1/jobs/{id}                       详情
  DELETE /api/v1/jobs/{id}                       删除
  POST   /api/v1/jobs/{id}/dispatch             下发 (MQTT)
  POST   /api/v1/jobs/{id}/cancel               取消
  GET    /api/v1/jobs/{id}/tasks                任务列表

任务:
  GET    /api/v1/tasks/{id}                      详情
  POST   /api/v1/tasks/{id}/retry                重试

文件:
  GET    /api/v1/download/parcels/{sid}/geojson  子地块下载
  GET    /api/v1/download/paths/{tid}.bin        路径下载 (MsgPack)

推送:
  GET    /api/v1/events/status                   SSE 流
```

---

## 5. 前端页面

| 路由 | 页面 | 核心功能 |
|------|------|----------|
| `/` | FarmMapView | Leaflet 地图 + 高德瓦片, 地块图层, 手绘地块, 分割预览 |
| `/machines` | MachineDashboard | 在线/忙碌/离线统计, 待确认设备列表, 确认注册 |
| `/jobs` | JobListView | 作业历史表, 状态筛选, 删除 |
| `/jobs/create` | JobCreateView | 3步向导: 选择操作 → 分割配置 → 确认下发 |
| `/jobs/:id` | JobDetailView | JobTimeline 时间线, 任务进度条, 重试按钮 |
| `/settings` | SettingsView | MQTT 配置, 注册机器, 农场参考点 |

### 实时更新
- **SSE 主通道**: 心跳事件 → 机器状态, 任务状态事件 → 进度更新
- **HTTP 轮询降级**: SSE 断线时每 10s 轮询
- **JobDetail**: running 状态每 5s 拉取详情

### 地图交互
- 点击地块 → 选中高亮 → 侧栏显示详情 → "新建作业"
- "绘制地块"按钮 → crosshair 模式 → 点击加顶点 → 双击完成 → 命名弹窗 → API 创建

---

## 6. MQTT Topic 与消息

| Topic | QoS | 方向 | 消息类型 |
|-------|-----|------|----------|
| `nodeflow/{id}/task/dispatch` | 1 | 云端→边侧 | TaskDispatch |
| `nodeflow/{id}/task/cancel` | 1 | 云端→边侧 | TaskCancel |
| `nodeflow/{id}/status` | 0 | 边侧→云端 | TaskStatus |
| `nodeflow/{id}/heartbeat` | 0 | 边侧→云端 | Heartbeat |
| `nodeflow/{id}/task/ack` | 1 | 边侧→云端 | TaskAck |

消息格式详见 [CLOUD_INTEGRATION.md](CLOUD_INTEGRATION.md)。

---

## 7. 机器自动发现

**不需要手动输入 IP**。机制:

1. 边侧 TaskAgent 启动 → 连接 MQTT broker → 每 30s 发送心跳
2. 云端 `_handle_heartbeat` 收到未知 `machine_id` 的心跳 → 自动创建 `status="unregistered"` 的 Machine 记录
3. 前端 `/machines` 页面显示 "待确认设备" 列表
4. 操作员点击 "确认注册" → `POST /machines/{id}/confirm` → 状态变为 `online`

边侧只需配置一个环境变量 `NF_MQTT_BROKER` 指向 broker 地址。

---

## 8. 端到端测试

```bash
# 集成测试工具
python3 tests/e2e_cli.py

# 子命令
start           启动所有服务 (mosquitto + cloud + daemon + agent)
status          查看状态
test [-w]       运行测试场景, -w 等待结果
watch           实时监控 (Ctrl+C 退出)
stop            停止所有服务
clean           停止 + 删除 DB + 清理 buffer
```

### 已验证的完整下发链路

```
Cloud POST /dispatch
  → MQTT publish task/dispatch (QoS 1)
    → Edge TaskAgent 接收 → ACK → TaskExecutor 写入 control buffer
      → Daemon poll → _apply_node_params → start_dataflow()
        → NodeLauncher 子进程启动 (--params 注入参数)
  ← TaskAgent 上报 DOWNLOADING → READY → RUNNING (MQTT status)
```

---

## 9. 启动指南

### 开发环境

```bash
# 1. 启动 MQTT broker (macOS)
/opt/homebrew/sbin/mosquitto -p 1883 &

# 2. 启动后端
cd cloud/server
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080

# 3. 启动前端
cd cloud/web
npm install
npm run dev          # http://localhost:5173

# 4. 启动边侧 (另一个终端)
python3 -m runtime.main examples/tillage_operation.yaml --daemon
NF_MACHINE_ID=tractor-01 python3 -m runtime.task.agent_main
```

### 一键启动

```bash
python3 tests/e2e_cli.py start       # 启动全部
python3 tests/e2e_cli.py status      # 查看状态
```

---

## 10. 环境变量

### 云端
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NF_CLOUD_MQTT_BROKER` | localhost | MQTT broker 地址 |
| `NF_CLOUD_MQTT_PORT` | 1883 | MQTT 端口 |

### 边侧
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NF_MQTT_BROKER` | localhost | MQTT broker 地址 |
| `NF_MQTT_PORT` | 1883 | MQTT 端口 |
| `NF_MACHINE_ID` | hostname | 机器唯一 ID |
| `NF_TASK_AUTO_ACCEPT` | true | 自动接受任务 |
| `NF_HTTP_SERVER_URL` | http://localhost:8080 | 云端文件下载地址 |
