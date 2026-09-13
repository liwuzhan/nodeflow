# 模块审阅报告：cloud/web（云端前端）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅（vue-tsc 0 错误）| 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 按上机边界重新评定后：本模块问题（ParcelSummary 无 geojson、SSE、错误处理等）**不属于当前边侧上机范围**；启用云端平台时重新成为门禁。详细映射见汇总报告第零节。

## 1. 模块职责

Vue 3 + Element Plus + Leaflet 云端管理前端：地图（地块/机器）、机器仪表盘、作业列表/创建/详情、设置页、SSE 实时推送、Pinia 状态管理。

| 目录 | 文件数 | 行数 |
|---|---|---|
| views/ | 6 | 772 |
| components/ | 13 | 644 |
| services/ | 6 | 188 |
| stores/ | 5 | 161 |
| models/ | 5 | 153 |
| router/ + utils/ + App/main | 5 | 144 |
| **src/ 合计** | **40** | **2,062** |

另含 web/monitor/ 独立子应用（9 文件 194 行）。

## 2. 页面与路由

| 路由 | 页面 | 功能 |
|---|---|---|
| `/` | FarmMapView | 运营摘要、Leaflet 地图（地块/分割预览/机器标记）、地块侧栏 |
| `/machines` | MachineDashboard | 统计、待确认设备、状态筛选、机器卡片 |
| `/jobs` | JobListView | 作业表格、草稿删除 |
| `/jobs/create` | JobCreateView | 三步向导（步骤→分割预览+机器分配→确认下发） |
| `/jobs/:id` | JobDetailView | 作业信息、步骤时间线、任务表、下发/取消/重试、5s 轮询 |
| `/settings` | SettingsView | MQTT 信息卡、注册机器、ENU 参考系 |

## 3. 发现的问题

### P0（核心功能失效）

1. **地图上无法显示已有地块多边形（首页核心功能失效）**（已验证根因 C14）：`listParcels` 后端返回 `ParcelSummary`（仅 id/name/area_ha/created_at，**无 geojson**），而 `ParcelLayer.vue:44` 直接用 `parcel.geojson` 渲染 → 刷新页面后地图只剩空图层。佐证：monitor 子应用正确单独调 fetchParcelDetail 拉取 geojson。

### P1（高）

2. **地块选中高亮/样式永不更新**：layer 创建时 isSelected 被捕获进 style，watch 后已存在 layer 被 continue 跳过（ParcelLayer.vue:42-51,62）。
3. **新建作业"确认并下发"失败时重复建单**：handleConfirm 先 createJob 再 dispatch 且无 try/catch——dispatch 失败（如坐标未配置 409）无提示，再次点击再建一份重复作业（JobCreateView.vue:199-223）。
4. **多处关键操作无错误处理（unhandled rejection）**：JobDetailView 的 fetchJobDetail/handleDispatch/handleCancel/handleRetry 全部裸 await；JobListView handleDelete、MachineDashboard handleConfirm 失败无提示。
5. **monitor 子应用 SSE 端点不存在**：`/api/v1/events/stream` vs 后端实际 `/api/v1/events/status` → monitor 实时状态完全失效（web/monitor/composables/useSSE.ts:14）。
6. **机器地图标记不随状态变化**：marker 仅 setLatLng 更新位置，状态变化不更新颜色/文案（MachineMarker.vue:32-41）。

### P2（摘选）

- SSE 重连固定 3s 无退避；onerror 多次触发可产生多个并发 EventSource；无连接级心跳。
- JobDetailView 轮询不停止（终态后仍 5s 轮询）。
- Element Plus 版本漂移（package.json ^2.5.0 实际 2.13.7）；`el-radio label` 弃用 API。
- `app.use(ElementPlus, { locale: { el: {} } })` 空翻译对象 → 内置文案回退英文（main.ts:10）。
- API 基址硬编码 `/api/v1`，env.d.ts 声明的 VITE_API_BASE_URL 从未使用。
- `onlineCount = status !== 'offline'` 把 busy/error/unregistered 全部计入"在线"。
- 死代码：mapStore.showParcels/showMachines、uiStore.showParcelDrawer 无消费方；geo.ts computeBounds/centerOf 未引用。
- api.ts 无超时（请求可无限挂起）；422 时 detail 数组 → new Error 显示 [object Object]。
- index.html Leaflet CSS 走 unpkg CDN，内网部署地图样式全毁。
- monitor 子应用 `Parcel.area_hectares` vs 后端 `area_ha` 字段漂移。

## 4. API 对接分析

| 前端调用 | 后端路由 | 一致性 |
|---|---|---|
| 全部 `/api/v1/*` 通过 vite proxy → 8080 | 与 HTTP_SERVER_PORT=8080 | ✅ |
| 6 个业务页面所有端点（machines/parcels/jobs/tasks/settings/events/status） | routers 实际注册 | ✅ 路径全匹配 |
| monitor `/events/stream` | 后端只有 `/events/status` | ❌ 漂移 |
| dispatchJob/cancelJob/jobDetail 响应类型 | Pydantic schema | ✅ 字段对齐 |
| JobCreate planning_mode/fallback 枚举 | contracts/task.py | ✅ 一致 |

`vue-tsc --noEmit` 0 错误（TS 层健康，问题在契约/逻辑层）。

## 5. 总体评价

**优点**: 分层清晰（services/stores/models 职责分明）；SSE 载荷与后端逐字段对齐；TS 严格模式零编译错误；API 路径全部匹配；类型契约质量好。

**主要风险**: P0-1 使首页地图核心功能失效；错误处理系统性缺失导致操作失败无感知 + 重复数据；SSE 半开连接无法自愈。

**建议优先修复**: P0-1（ParcelSummary 增加 geojson 或前端对列表项补拉 detail）、P1-3（handleConfirm 整体 try/catch + dispatch 失败时删除刚建的 draft）、P1-5（monitor 端点对齐）、P1-2（选中状态样式响应式更新）。
