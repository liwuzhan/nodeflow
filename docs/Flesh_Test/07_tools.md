# 模块审阅报告：tools（CLI / MCP / 运行时管理 / GUI / 编辑器）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 按上机边界重新评定后：**P1 #7（CLI runtime start 固定 sleep(2)）升格为当前 P1**——模型直接调用 CLI 是当前使用方式，边侧机器可能比开发机慢，需改为带超时状态轮询或样机重点验证；P1 #1/#2/#3（MCP 整体失效）归档（MCP 不在运行链路，标记为不支持）；GUI/web-editor 问题全部排除。详细映射见汇总报告第零节。

## 1. 模块职责

| 模块 | 文件/行数 | 职责 |
|---|---|---|
| tools/cli | cli.py 618 + commands/*.py + utils | `nodeflow` 命令：node/buffer/health/simulator/monitor/runtime/task/logs 9 组 |
| tools/mcp/mcp_server.py | 962 | MCP stdio server，9 个工具 |
| tools/runtime_manager.py | 459 | PID 管理、进程状态查询、start/stop（供 MCP 使用） |
| tools/preflight_runtime.py | 440 | 启动前检查（simulator+daemon → 9 缓冲就绪 → 位移验证 → 干净关闭契约） |
| tools/debug_runtime.py | 366 | 8 步启动诊断 |
| tools/test_reporter.py | 426 | 测试报告生成器 |
| tools/gui/gui_runtime_control.py | 529 | tkinter 控制面板 |
| tools/install_node_deps.py | 219 | 节点依赖安装 |
| tools/editor/web-editor/ | src 6,662 | Vue3+VueFlow 图编辑器前端 |

**去重后 34 个文件 / 6,249 行**（另 `tools/cli/cli/` 嵌套重复树 17 文件 / 2,813 行）。

## 2. 命令与工具清单

- **CLI**: `node list|info`、`buffer list|inspect|read`、`health check|status|flow`、`simulator refresh`、`monitor`、`runtime start|stop|status|start/stop/restart-dataflow`、`task run|list|show|cancel`、`logs`
- **MCP**: get-node-info / validate-yaml / edit-yaml / run-runtime / stop-runtime / read-logs / get-runtime-status / buffer-read / node-health

## 3. 发现的问题

### P1（高）

| # | 位置 | 问题 |
|---|---|---|
| 1 | `mcp_server.py:83` | **MCP 路径根目录错误（已实测）**：`resolve_project_path` 用 `Path(__file__).parent`（= tools/mcp）当 project_root → 所有相对路径解析到不存在的 tools/mcp/xxx，仓库内绝对路径被误判"在项目外"拒绝 → get-node-info/validate-yaml/edit-yaml/run-runtime 实际全部不可用。 |
| 2 | `mcp_server.py:44` | **MCP 导入链失效**：`from runtime_manager import ...` 需 tools/ 在 sys.path；README 仍指导根目录 `python3 mcp_server.py`（文件已移走，import 必然失败）。 |
| 3 | `pytest.ini:11` + `tests/mcp/test_error_responses.py:15` | **MCP 测试套件整体失效**：mcp 被 norecursedirs 排除；直接运行又因 `from mcp_server import` 失败。 |
| 4 | `test_reporter.py:60,67,93,126` | **test_reporter 在目录重组后报废**：语法检查 glob 指向已删除的 `runtime/**`、`sdk/*.py`（现 edge/runtime、edge/sdk）；mock 节点目录全部不存在 → 恒 fail。 |
| 5 | `cloud/server/routers/editor.py:103-114` | **HTTP runtime 控制端点无鉴权 + config_path 无路径包含校验**（可 `../` 越出项目根，仅 exists 检查）——与 cloud 报告 P0 同源。 |
| 6 | web-editor 接线断裂 | (a) vite proxy 指向 8000，cloud server 实际 8080；(b) 前端请求 `/api/nodes`，后端实际 `/editor/api/nodes`；(c) start_web_editor.sh 引用已删除的 web-editor/backend/node-hub 目录。 |
| 7 | `commands/runtime_cmd.py:100-112` | **CLI runtime start 后台竞态**：固定 sleep(2) 后查 PID 文件，daemon 初始化（节点库扫描）>2s 时误报失败，进程继续后台启动 → "孤儿控制"。 |
| 8 | `runtime_manager.py:211-218` | start_runtime 与 CLI 语义不一致（run() 模式 vs daemon 模式）；硬编码 `"python3"` 而非 sys.executable。 |
| 9 | `commands/logs_cmd.py:29-32,133-135` | **logs 命令被单条坏日志行击穿**：`datetime.fromisoformat` ValueError 未捕获（仅捕获 JSONDecodeError）→ 任一损坏行使整个命令崩溃。 |
| 10 | `commands/buffer_cmd.py:139-141,160` | buffer inspect 无长度/深度限制（uint32 length 最大 4GB 直接 read → 内存耗尽）；name 参数无 `../` 过滤。 |
| 11 | `install_node_deps.py:146,31` | 默认路径 `node-hub`（实际 edge/nodes），只扫描一层目录。 |

### P2（摘选）

- `tools/cli/cli/` 与 `tools/cli/` 全套重复（17 文件 2,813 行死代码维护陷阱）。
- MCP 默认 hub 路径 `./node-hub` 过期（实际 edge/nodes）。
- preflight 端口 8080 假阳性（与 cloud server 及 trajectory_viz 冲突）；REQUIRED_BUFFERS 绑定特定配置。
- runtime status Linux-only（读 /proc，macOS 裸 except: pass）。
- `/tmp/nodeflow_runtime.pid` 普通 "w" 打开（无 O_NOFOLLOW、无权限收紧）。
- GUI：`root.after` 跨线程非线程安全；_handle_stop_result 无论成败都打"已停止"。
- `find_node_manifest` 子串匹配（"gps" 命中 "gps_imu"）。
- logs_cmd 的 `config` 位置参数解析后从未使用。
- debug_runtime step_6 仍为 "ZMQ addresses"（IPC 已去 ZMQ）。
- monitor_cmd 对迟到缓冲区不重试（永久 MISSING）。
- preflight 8080 与 trajectory_viz web_port 默认 8080 冲突。

## 4. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C2: `resolve_project_path("examples/planning_simulation.yaml")` 解析到 tools/mcp/examples/... 而非仓库根 | **确认（P1 #1）** |
| C9: pytest 收集 443 项，mcp/legacy 被 norecursedirs 排除 | **确认（P1 #3 的一部分）** |

## 5. 总体评价

**优点**: CLI 主体（node/buffer/health/logs/runtime/task）实现完整；health 流活性判定（OK/IDLE/STALE/MISSING）与停止三级策略（缓冲→SIGTERM→SIGKILL+PWM 复位）质量较高。

**主要风险**: 8 月目录重组（9e7bd83）后的系统性遗留——MCP server 路径根错误致整服务失效、MCP 测试被排除且导入断裂、test_reporter/start_web_editor.sh/install_node_deps 指向旧目录、web-editor 前后端路由与端口脱节；叠加 editor.py 无鉴权控制面。

**建议优先修复**: P1 #1（project_root 改 `Path(__file__).resolve().parent.parent.parent` 即仓库根）、P1 #2（README 更新为 `python3 -m tools.mcp.mcp_server` 或脚本化启动）、P1 #5（config_path 路径包含校验）、P1 #6（vite proxy/路由对齐）。
