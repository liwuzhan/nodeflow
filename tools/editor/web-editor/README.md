# NodeFlow Web Blueprint Editor

基于 Vue 3、TypeScript、Vue Flow、Pinia 和 Element Plus 的可视化运行图编辑器。

## 当前功能

- 浏览和搜索 `edge/nodes/` 中的 manifest；
- 拖放节点、连接端口、平移/缩放和小地图；
- 编辑节点参数、分组和注释；
- 检查节点引用、端口方向和类型兼容性；
- 导出 Runtime YAML，并保存到后端的 `examples/`；
- 导入/导出 `.nfproj.json` 项目文件；
- 选择示例配置，控制 Runtime/Dataflow 并查看 Runtime 日志。

编辑器是配置和运维辅助工具。Runtime 的 YAML/manifest 校验仍是执行前的最终门槛；端口类型相同也不保证 payload 字段语义完全一致。

## 后端

编辑器后端已经合入 `cloud/server/routers/editor.py`，随 `cloud.server.app` 启动，API 挂在 `/editor/api`：

```bash
# 仓库根目录
python -m pip install -r cloud/server/requirements.txt
python3 -m uvicorn cloud.server.app:app --host 127.0.0.1 --port 8080
```

主要端点：

| API | 用途 |
|---|---|
| `GET /editor/api/nodes` | 列出节点包 |
| `GET /editor/api/nodes/{package}/manifest` | 获取 manifest |
| `GET /editor/api/examples` | 列出示例配置 |
| `POST /editor/api/export/save` | 保存 YAML 到 `examples/` |
| `POST /editor/api/runtime/start|stop` | 控制 Runtime |
| `POST /editor/api/runtime/dataflow/{action}` | 启停/重启数据流 |
| `GET /editor/api/runtime/status|logs` | 查看状态和日志 |

## 前端开发

```bash
cd tools/editor/web-editor
npm install
VITE_API_BASE_URL=http://localhost:8080/editor/api npm run dev
```

默认开发端口是 5173。显式设置 `VITE_API_BASE_URL` 可以让当前 Cloud 端口和路由前缀保持清晰，不依赖本地代理配置。

构建：

```bash
npm run build
```

## 源码结构

```text
src/
├── components/
│   ├── canvas/       # 图画布、节点、边和端口
│   ├── dialogs/      # 导出与校验
│   ├── layout/       # 主布局和工具栏
│   ├── library/      # 节点库
│   ├── properties/   # 参数、分组和注释
│   └── runtime/      # Runtime 控制和日志
├── models/           # manifest、Runtime、项目和分组类型
├── services/         # API、验证、YAML 和项目持久化
├── stores/           # graph、node library、runtime、UI、group
└── views/            # Runtime 视图
```

## 已知边界

- 编辑器后端和 Cloud API 同进程运行，但二者 URL 前缀不同。
- “保存到 examples”会写仓库文件，使用前应确认文件名和覆盖意图。
- 当前前端、后端路由和 Runtime 控制需要在目标环境单独做集成验证。
- 生产部署应配置认证、CORS、反向代理和写入权限；默认 Cloud 配置只适合受控开发网。

系统工具总览见 [docs/SIMULATION_AND_TOOLS.md](../../../docs/SIMULATION_AND_TOOLS.md)。
