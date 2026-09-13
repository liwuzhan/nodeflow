# NodeFlow 云端管理平台 — 前端页面与使用逻辑

> 最后更新: 2026-05-01  
> 前端项目: `cloud/web/`  
> 技术栈: Vue 3 + TypeScript + Vite + Pinia + Element Plus + Leaflet

---

## 1. 总览

| 页面 | 路由 | 核心功能 |
|------|------|----------|
| 农场地图 | `/` | 卫星地图、地块管理、手绘地块、分割预览 |
| 机器监控 | `/machines` | 实时状态面板、自动发现确认、心跳追踪 |
| 作业列表 | `/jobs` | 作业历史、状态筛选、快速创建入口 |
| 创建作业 | `/jobs/create` | 3 步向导：选操作 → 分割分配 → 确认下发 |
| 作业详情 | `/jobs/:id` | 时间线、任务进度表、下发/取消/重试 |
| 系统设置 | `/settings` | MQTT 配置、机器注册、农场参考点 |

### 页面关系

```
FarmMapView ────────────── 默认着陆页
  │  地块选中 → "新建作业" → JobCreateView
  │
  ├── SideNav ──→ MachineDashboard
  │               │  待确认设备 → 确认注册
  │
  ├── SideNav ──→ JobListView
  │              │  点击行 → JobDetailView
  │              │  新建 → JobCreateView
  │
  └── SideNav ──→ SettingsView
```

---

## 2. 农场地图 — `FarmMapView`

**路由**: `/`  
**组件**: `FarmMap`, `ParcelLayer`, `SplitPreview`, `ParcelDrawer`, `MachineMarker`  
**Store**: `parcelStore`, `mapStore`

### 界面布局

```
┌──────────────────────────────────────┬─────────────┐
│                                      │  地块列表     │
│        Leaflet 卫星地图               │  ────────   │
│   ┌─────────────────────┐            │  Field A    │
│   │  [绘制地块]          │            │  1.2 ha     │
│   └─────────────────────┘            │  Field B ✓  │  ← 选中
│                                      │  0.8 ha     │
│   ▨ Field A (绿色边框)                │             │
│   ▨ Field B (蓝色边框 ← 选中)         │ [新建作业]   │
│                                      │             │
│   ● tractor-01 (绿色=在线)            │             │
└──────────────────────────────────────┴─────────────┘
```

### 使用逻辑

1. **查看地块**: 地图加载后自动渲染所有已注册地块的多边形图层，填充半透明色，显示名称和面积 tooltip
2. **选中地块**: 点击地图上的地块多边形 → 边框变蓝、侧栏高亮 → 可查看详情或创建作业
3. **绘制地块**: 点击顶部「绘制地块」按钮 → 鼠标变成十字 → 点击地图添加顶点 → 双击完成 → 弹出命名对话框 → 提交创建
4. **分割预览**: 在创建作业的第 2 步触发分割预览后，地图上叠加子地块彩色图层（每条不同颜色），含机器分配标签
5. **机器标记**: 在线机器显示绿色圆点、忙碌黄色、离线灰色，悬停显示名称和状态
6. **刷新**: 侧栏标题右侧有刷新按钮，重新拉取地块列表

### 状态管理

```
parcelStore
  ├── parcels[]          地块列表
  ├── selectedParcelId   当前选中的地块 ID
  ├── splitPreview[]     分割预览的子地块
  ├── fetchParcels()     拉取列表
  ├── addParcel()        创建地块
  ├── removeParcel()     删除地块
  ├── fetchSplitPreview()  请求分割预览
  └── selectParcel()     选中/取消地块

mapStore
  ├── center / zoom      地图视口
  ├── showParcels        地块图层开关
  ├── showSplitPreview   分割预览图层开关
  └── showMachines       机器标记开关
```

---

## 3. 机器监控 — `MachineDashboard`

**路由**: `/machines`  
**组件**: `MachineGrid`, `MachineCard`, `StatusBadge`  
**Store**: `machineStore`

### 界面布局

```
统计:  在线 2    忙碌 1    离线 0

━━ 待确认设备 [1] ━━
┌──────────────┐
│ Tractor-1    │  [未确认]
│ 类型 tractor  │
│              │
│  [确认注册]   │
└──────────────┘

━━ 已注册机器 ━━
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Tractor-2    │  │ Tractor-3    │  │ Harvester-1  │
│ [在线]        │  │ [忙碌]       │  │ [离线]        │
│ CPU 12%      │  │ CPU 45%      │  │ 心跳: 无     │
│ 内存 256MB   │  │ 内存 512MB   │  │ 透明度 0.6   │
│ 运行 10h     │  │ 运行 3h      │  │              │
│              │  │ task: abc..  │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

### 使用逻辑

1. **查看状态**: 顶部统计栏显示在线/忙碌/离线数量
2. **待确认设备**: 边侧 TaskAgent 上线后发心跳 → 云端自动创建 `status=unregistered` → 在此区域显示，带「确认注册」按钮
3. **确认注册**: 点击「确认注册」→ `POST /machines/{id}/confirm` → 状态变为 online → 卡片移到已注册区域
4. **状态指示**: 卡片左边框颜色 — 绿色在线、橙色忙碌、灰色离线（透明度降低）
5. **实时更新**: 通过 5 秒 HTTP 轮询（`machineStore.startPolling`）或 SSE 心跳事件自动刷新
6. **忙碌任务**: 忙碌机器的卡片底部显示当前执行的 task_id 缩写

### 状态管理

```
machineStore
  ├── machines[]          机器列表
  ├── onlineCount         在线数 (computed)
  ├── busyCount           忙碌数 (computed)
  ├── offlineCount        离线数 (computed)
  ├── fetchMachines()     拉取列表
  ├── startPolling(ms)    开始轮询 (默认 5s)
  └── stopPolling()       停止轮询
```

---

## 4. 作业列表 — `JobListView`

**路由**: `/jobs`  
**组件**: `el-table`, `StatusBadge`  
**Store**: `jobStore`

### 界面布局

```
━━ 作业管理 ━━━━━━━━━━━━━━━━━━━━━━ [新建作业]
┌──────────┬──────────┬────────┬──────┬──────────┬────────────┬────────┐
│ ID       │ 名称     │ 状态   │ 分割 │ 步骤数    │ 创建时间    │ 操作   │
├──────────┼──────────┼────────┼──────┼──────────┼────────────┼────────┤
│ job-...  │ Job-001  │ [运行中]│ strip│ 2 步     │ 05-01 08:00│ 详情 删除│
│ job-...  │ Field-A  │ [完成]  │ strip│ 1 步     │ 04-30 15:00│ 详情      │
│ job-...  │ Draft-1  │ [草稿]  │ —    │ 1 步     │ 04-30 14:00│ 详情 删除│
└──────────┴──────────┴────────┴──────┴──────────┴────────────┴────────┘
```

### 使用逻辑

1. **查看历史**: 表格列出所有作业，按创建时间倒序，显示 ID、名称、状态标签、分割模式、步骤数
2. **进入详情**: 点击「详情」→ 跳转 `/jobs/:id`
3. **删除草稿**: 仅 `draft` 状态的作业可删除，running 状态不可删除
4. **新建**: 点击右上角「新建作业」→ 跳转 `/jobs/create`

### 状态管理

```
jobStore
  ├── jobs[]              作业列表
  ├── activeJobs          运行中作业 (computed)
  ├── fetchJobs(status?)  拉取列表（可筛选状态）
  └── removeJob(id)       删除作业
```

---

## 5. 创建作业 — `JobCreateView`

**路由**: `/jobs/create`  
**Store**: `parcelStore`, `machineStore`, `jobStore`

### 3 步向导

```
┌─────────────────────────────────────────────────────┐
│  ● Step 1: 选择操作  ──  ○ Step 2: 分割分配  ──  ○ Step 3: 确认下发  │
└─────────────────────────────────────────────────────┘
```

### Step 1 — 选择操作

```
地块:  [▼ Field B (1.2 ha)]

操作步骤:
┌──────────────────────────────────────────────┐
│ [▼ 旋耕]  [▼ tillage_operation]   [✕]       │
│ [▼ 播种]  [▼ tillage_operation]   [✕]       │
└──────────────────────────────────────────────┘
[+ 添加步骤]

                              [下一步 →]
```

**交互**:
- 下拉选择已注册地块
- 每行选操作类型（旋耕/播种/喷洒）和 preset YAML
- 支持多条步骤，自动生成依赖链（Step N 依赖 Step N-1）
- 可删步骤（至少保留 1 条）

### Step 2 — 分割与分配

```
分割模式:  (●) 条带分割  ( ) 网格分割
份数:      [2 ▼]
[预览分割]  ← 触发 POST /parcels/{id}/preview-split

机器分配:
  Section 1 (0.55 ha) → [▼ Tractor-1]
  Section 2 (0.56 ha) → [▼ Tractor-2]

提示: 在农场地图页面可看到分割预览效果

              [上一步]  [下一步 →]
```

**交互**:
- 选择分割模式和份数
- 点击「预览分割」→ 后端计算 → `splitPreview` 存到 `parcelStore` → 地图组件 `SplitPreview` 自动渲染彩色子地块
- 每个子地块分配一台机器

### Step 3 — 确认下发

```
┌──────────────────────┬──────────────┐
│ 地块                  │ Field B      │
│ 分割                  │ strip ×2    │
│ 步骤数                │ 2           │
│ 机器数                │ 2           │
│ Step 1               │ 旋耕 — tillage│
│ Step 2 (依赖 Step 1)  │ 播种 — tillage│
└──────────────────────┴──────────────┘

              [上一步]  [确认并下发]
```

**交互**:
- 汇总展示所有配置
- 点击「确认并下发」→ 创建 Job → 自动调用 dispatch → 跳转 JobDetailView

### 注意

- 表单状态仅在内存中，导航离开会丢失
- 改变 `splitCount` 后需重新预览分割和分配机器

---

## 6. 作业详情 — `JobDetailView`

**路由**: `/jobs/:id`  
**组件**: `JobTimeline`, `StatusBadge`  
**Store**: `jobStore`

### 界面布局

```
← 返回    Job-Field-B-001    [运行中]

作业 ID: job-...   地块 ID: xxx   分割: strip ×2

━━ 任务时间线 ━━
  ● Step 0: 旋耕 — tillage_operation [运行中]
  │  ┌──────────────────────────────────────────┐
  │  │ tractor-01  [下载中] ████░░░░░░░░ 40%    │
  │  │ tractor-02  [就绪]   ░░░░░░░░░░░░░░ 0%   │
  │  └──────────────────────────────────────────┘
  │
  ○ Step 1: 播种 — tillage_operation [等待中]
     ← 依赖 Step 0

━━ 任务详情 ━━
┌──────────┬────────┬─────────────┬──────────┬────────┐
│ 机器     │ 状态   │ 进度        │ 错误码    │ 操作   │
├──────────┼────────┼─────────────┼──────────┼────────┤
│tractor-01│ running│ ████ 40%   │ —        │        │
│tractor-02│ ready  │ ░░░░ 0%    │ —        │        │
└──────────┴────────┴─────────────┴──────────┴────────┘

                                   [取消作业]
```

### 使用逻辑

1. **查看进度**: 时间线展示每个 step 的状态和下属 task 的进度条
2. **实时更新**: running 状态的作业每 5 秒自动轮询刷新，SSE `task_status` 事件也会实时更新进度
3. **下发**: draft/ready 状态点击「下发执行」→ 触发 MQTT dispatch
4. **取消**: running 状态点击「取消作业」→ 发送 MQTT cancel → daemon 停止数据流
5. **重试**: 失败的 task 行显示「重试」按钮 → `POST /tasks/{id}/retry`

### 状态管理

```
jobStore
  ├── currentJob          当前作业详情
  ├── fetchJobDetail(id)  拉取详情
  ├── dispatch(id)        下发执行
  ├── cancel(id)          取消作业
  └── updateTaskProgress() SSE 事件 → 更新 task 进度（实时）
```

---

## 7. 系统设置 — `SettingsView`

**路由**: `/settings`

### 界面布局

```
━━ 系统设置 ━━

┌─ MQTT Broker ──────────────────────────┐
│ Broker 地址: localhost                  │
│ 端口:        1883                       │
│ Cloud Client: nodeflow-cloud            │
│ 通过环境变量 NF_CLOUD_* 配置            │
└────────────────────────────────────────┘

┌─ 注册新机器 ───────────────────────────┐
│ 机器 ID:  [           ] (如 tractor-02) │
│ 名称:    [           ] (如 2号拖拉机)   │
│ 类型:    [▼ 拖拉机]                    │
│ 幅宽(m): [2.0 ▼]                       │
│                      [注册]             │
└────────────────────────────────────────┘

┌─ 农场参考点 ───────────────────────────┐
│ 经度: 120.037328                        │
│ 纬度: 28.91685                          │
│ 参考点用于 GPS↔ENU 坐标转换            │
└────────────────────────────────────────┘
```

### 使用逻辑

1. **查看 MQTT 配置**: 显示当前 broker 地址和端口（只读，通过环境变量配置）
2. **手动注册机器**: 填写机器 ID + 名称 + 类型 + 幅宽 → 提交 → 调用 `POST /machines`
3. **自动发现备选**: 边侧 TaskAgent 上线后通过 MQTT 心跳自动发现，在 MachineDashboard 页面确认注册，无需在此手动填写

---

## 8. 实时数据流

### SSE 主通道

```
Cloud Backend                    Frontend (App.vue)
     │                                  │
     │── SSE /events/status ──────────→ │ EventSource
     │                                  │
     │  event: heartbeat                 ├─→ machineStore.machines[i].status
     │  data: {machine_id, status, ...} │
     │                                  │
     │  event: task_status               ├─→ jobStore.updateTaskProgress()
     │  data: {edge_task_id, state, %}  │   (currentJob.edge_tasks 实时更新)
```

### HTTP 轮询降级

- **机器列表**: SSE 断线时每 10 秒轮询 `GET /machines`
- **作业详情**: running 状态每 5 秒轮询 `GET /jobs/{id}`，非 running 状态不轮询

### 状态一致性

- SSE 事件更新是**增量**的（只改对应字段），轮询是**全量**的（整表替换），两者互补
- `jobStore.updateTaskProgress()` 在 `currentJob` 为 null 时不操作 — SSE 事件先于详情加载到达时会丢失（已知限制，ROADMAP）

---

## 9. 组件树

```
App.vue
└── CloudLayout.vue
    ├── SideNav.vue                    # 左侧导航: 地图 / 机器 / 作业 / 设置
    ├── TopBar.vue                     # 顶部: 标题 + 在线/离线数量
    └── <router-view />
        │
        ├── FarmMapView.vue
        │   ├── FarmMap.vue            # L.map 实例 (provide leafletMap)
        │   │   ├── L.tileLayer        # 高德卫星图
        │   │   ├── ParcelLayer        # 地块 GeoJSON 图层
        │   │   ├── SplitPreview       # 子地块彩色覆盖层
        │   │   ├── ParcelDrawer       # 手绘模式 (crosshair + 双击完成)
        │   │   └── MachineMarker      # 机器状态圆点
        │   └── 侧栏: 地块列表 + 新建作业按钮
        │
        ├── MachineDashboard.vue
        │   ├── el-statistic ×3        # 在线/忙碌/离线
        │   ├── MachineGrid (待确认)    # unregistered 机器 + 确认按钮
        │   └── MachineGrid (已注册)    # online/busy/offline 机器卡片
        │
        ├── JobListView.vue
        │   └── el-table               # 作业历史表
        │
        ├── JobCreateView.vue
        │   ├── el-steps               # 3步进度指示
        │   ├── Step1: el-form         # 地块下拉 + 操作步骤行
        │   ├── Step2: el-form         # 分割配置 + 预览按钮 + 机器分配
        │   └── Step3: el-descriptions # 确认汇总表
        │
        ├── JobDetailView.vue
        │   ├── el-descriptions        # 作业摘要
        │   ├── JobTimeline.vue        # el-timeline + 每步任务进度条
        │   └── el-table               # 任务详情表 (含重试按钮)
        │
        └── SettingsView.vue
            ├── el-card (MQTT)         # 只读配置显示
            ├── el-card (注册机器)      # 手动注册表单
            └── el-card (农场参考点)    # 只读坐标
```

---

## 10. 关键数据流示例

### 创建作业全流程

```
1. FarmMapView: 点击地块 Field B → parcelStore.selectParcel(id)
2. 点击 "新建作业" → router.push('/jobs/create')
3. JobCreateView Step1: 选择 Field B → 添加 tillage + seeding 步骤
4. Step2: strip ×2 → 点击预览分割
   → parcelStore.fetchSplitPreview()
   → POST /parcels/{id}/preview-split
   → SplitPreview 组件 watch(splitPreview) → 渲染彩色子地块
5. Step2: 分配 tractor-01 → Section1, tractor-02 → Section2
6. Step3: 确认 → jobStore.addJob()
   → POST /jobs
   → jobStore.dispatch()
   → POST /jobs/{id}/dispatch
   → 后端: Dispatcher.dispatch_job() → MQTT publish
7. router.push('/jobs/{id}') → JobDetailView
8. JobDetailView: startPolling(5s) → 实时进度 + JobTimeline
```

### 自动发现机器

```
1. 边侧: TaskAgent 启动 → MQTT connect → 每30s 发 heartbeat
2. 云端: mqtt_client._handle_heartbeat → machine_id 未知
   → 自动创建 Machine(status="unregistered")
   → SSE publish "heartbeat" 事件
3. 前端: SSE → machineStore.machines 更新
   → MachineDashboard 显示 "待确认设备"
4. 操作员: 点击 "确认注册" → POST /machines/{id}/confirm
   → status → "online"
5. 后续心跳: status 保持 online/busy, 不再覆盖
```
