# 旧模块处置表

| 目录 | 状态 | 处置 |
|---|---|---|
| `backend/` | 保留 | 待合并到 `cloud/server/`，消除双 FastAPI |
| `gui/` | ✅ 已处置 | 移至 `tools/gui/`（tkinter 控制面板） |
| `other/` | ✅ 已处置 | 移至 `docs/archive/`（测试数据） |
| `runtime_manager.py` | ✅ 已处置 | 移至 `tools/runtime_manager.py` |
| `node-hub/` | ✅ 已删除 | 内容已移入 `edge/nodes/` |
| `node-back/` | ✅ 已删除 | 内容已移入 `edge/nodes/observability/` |
| `sdk/` | ✅ 已删除 | 内容已移入 `edge/sdk/` |
| `nodeflow_protocol/` | ✅ 已删除 | 内容已移入 `contracts/` |
| `simulator/` | ✅ 已删除 | 内容已移入 `simulation/` |
| `runtime/` | ✅ 已删除 | 内容已移入 `edge/runtime/` |
| `cloud/monitor/` | 保留 | 待合并到 `cloud/web/monitor/`（一个 Vite 多入口） |
| `cloud/web/admin/` | 保留 | 待从 `cloud/web/src/` 拆出管理后台路由 |
| `docs/` | 保留 | 开发文档 + 存档 |
| `examples/` | 保留 | 教学用途，生产配置已在 `configs/` |
