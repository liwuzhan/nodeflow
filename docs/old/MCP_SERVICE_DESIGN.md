# NodeFlow MCP 服务方案设计（基于 `tools/` 能力）

## 背景

当前数据流 `runtime.yaml` 主要由 Web 编辑器生成。与此同时，NodeFlow 的“节点详细信息”（节点说明书 `node.yaml`、端口、参数、入口点）都在本地 `node-hub/` 中，以结构化文件形式存在，并且运行时已经具备完整的配置解析、节点库扫描、图校验、拓扑排序与启动/监控能力。

如果将这些能力通过 MCP 以结构化方式暴露给 AI（读取节点说明书、校验 YAML、给出可机器消费的错误与建议），那么 `runtime.yaml` 就不一定必须由前端生成：AI 可以在“查询 → 生成 → 校验 → 运行验证 → 再修正”的闭环中参与整个调试过程。

本方案描述：如何将现有 `tools/` 目录中的 CLI/诊断/测试能力抽象为 MCP 服务，支持 AI 辅助生成与调试 NodeFlow 数据流 YAML。

## 目标

- 让 AI 能通过结构化接口获取节点库信息（包列表、manifest、端口/参数/入口点）。
- 让 AI 能对 `runtime.yaml` 执行确定性的校验（语法、字段、端口连线、类型、拓扑无环）。
- 让 AI 能在“安全可控”的范围内触发本机调试动作（例如运行诊断流程、运行测试、可选启动 runtime 并抓取日志/状态）。
- 形成可迭代的最小闭环：AI 写 YAML → MCP 校验 → 修正 → 再校验 → 可选运行验证。

## 非目标

- 不在 MCP 层提供任意命令执行（避免变成通用远控 Shell）。
- 不直接替代 Web 编辑器；MCP 是并行能力，供 AI/CLI/自动化使用。
- 不做跨机器的远程编排（先聚焦本机开发调试场景）。

## 现有能力与可复用入口

`tools/` 目前已经包含可复用的功能入口：

- 节点库查询（CLI）：`tools/cli/core/cli.py`、`tools/cli/commands/node_cmd.py`
  - `nodeflow node list --hub-path ...`
  - `nodeflow node info <package> --hub-path ...`
- 运行时诊断（脚本）：`tools/debug_runtime.py`
  - 逐步验证：解析 YAML、扫描 node-hub、加载 registry、图校验、拓扑排序、生成 socket 路径、检查节点脚本等
- 测试执行（脚本）：`tools/run_tests.sh`
  - 语法检查、mock 节点配置检查、场景 YAML 检查、pytest 单测、可选场景运行

运行时与配置层的可复用模块（供 MCP “校验/分析”调用，而不是复刻逻辑）：

- `runtime/config/yaml_parser.py`：解析 `runtime.yaml` 与 `node.yaml`
- `runtime/config/validator.py`：基础规则校验
- `runtime/node_hub/scanner.py`、`runtime/node_hub/node_registry.py`：扫描与加载节点说明书
- `runtime/graph/validator.py`、`runtime/graph/topology.py`：连线与拓扑

## MCP 服务形态

建议将 MCP 服务定位为“本机开发代理”，提供两种运行模式：

1. **只读/静态模式（默认）**
   - 仅提供：节点库查询、manifest 读取、YAML 解析与校验、拓扑分析。
   - 不启动 runtime、不写文件、不运行测试。

2. **调试/执行模式（显式开启）**
   - 允许：运行 `tools/debug_runtime.py` 的诊断流程；运行 `tools/run_tests.sh`；可选启动 `python -m runtime.main <yaml>` 并收集日志。
   - 所有执行类能力都需要：白名单、超时、输出截断、目录限制。

服务进程建议直接复用 Python 模块导入的方式（而不是 shell 调用 CLI），以得到稳定的结构化返回值；但对于 `run_tests.sh` 这类脚本，可以作为“受控命令”保留。

## 能力设计（Resources + Tools）

以下为 MCP 能力的逻辑分组与建议接口。命名仅为方案示例，实际以 MCP 工具注册时的名称为准。

### 1) Node Hub：节点库与说明书

- Tool: `nodehub.list_packages`
  - 输入：`hub_path`（可选，默认 `./node-hub`）
  - 输出：`packages: string[]`

- Tool: `nodehub.get_manifest`
  - 输入：`hub_path`（可选）、`package`（例如 `simulation/target_generator`）
  - 输出：
    - `manifest_raw`（原始 YAML 文本，可选）
    - `manifest`（结构化字段：`name/version/description/entrypoints/ports/params`）

- Tool: `nodehub.search`
  - 输入：`query`（按包名/描述匹配）
  - 输出：`matches`（包名与摘要信息）

### 2) YAML：生成辅助与校验

- Tool: `yaml.get_schema`
  - 输出：`runtime_yaml_schema`（以说明形式给出字段与约束）
  - 约束来源：`runtime/config/models.py` 与 `runtime/config/yaml_parser.py`

- Tool: `yaml.validate_runtime`
  - 输入：`yaml_text`（或 `yaml_path`，二选一）
  - 输出（结构化，便于 AI 修正）：
    - `is_valid: bool`
    - `errors: string[]`
    - `warnings: string[]`
    - `normalized`（可选：解析后的 `graph_id/nodes/edges` 结构）

校验逻辑建议组合：

1. `YAMLParser.parse_runtime_config()` 语法与字段解析（`edges.from/to` 必须为 `node.port` 格式）
2. `ConfigValidator.validate()` 基础规则
3. `NodeRegistry.load_all()` 加载 node-hub
4. `GraphValidator.validate()` 端口存在性、类型兼容性
5. `TopologyAnalyzer.topological_sort()` 无环验证并给出分层启动顺序

### 3) Graph：可解释的编排计划

- Tool: `graph.plan_startup_layers`
  - 输入：`yaml_text`（或 `yaml_path`）
  - 输出：
    - `layers: string[][]`（拓扑分层）
    - `dependencies`（可选：每个节点依赖列表）

用途：AI 在生成 YAML 时可以“先搭图”，再用该接口确认启动并行层级是否符合预期。

### 4) Diagnostics：按步骤输出的可复现诊断

- Tool: `diagnostics.run`
  - 输入：`yaml_path`（或 `yaml_text` + 临时路径策略）
  - 输出：
    - `steps: [{name, ok, details}]`
    - `summary: {passed, total}`

建议直接复用 `tools/debug_runtime.py` 中的步骤语义，但以模块方式调用其内部类/方法，避免解析 stdout。

### 5) Tests：受控测试执行

- Tool: `tests.run`
  - 输入：`mode`（`quick|full|scenario`）
  - 输出：
    - `exit_code`
    - `report_paths`（例如 `.test-reports/*.log`）
    - `tail`（末尾若干行，便于快速定位失败原因）

实现上可将 `tools/run_tests.sh` 作为白名单脚本执行，并强制超时与输出截断。

### 6) Runtime（可选）：本机启动与观测

这部分建议作为二期能力（或仅在“调试/执行模式”开启），因为涉及长运行进程、资源释放与安全控制。

- Tool: `runtime.start`
  - 输入：`yaml_path`、`duration_s`（可选，默认短时启动用于验证）、`log_dir`（可选）
  - 输出：`run_id`、`pid`、`log_paths`

- Tool: `runtime.status`
  - 输入：`run_id`
  - 输出：节点进程状态摘要（running/dead、退出码、最近心跳或启动时间等）

- Tool: `runtime.stop`
  - 输入：`run_id`
  - 输出：停止结果

- Tool: `runtime.tail_logs`
  - 输入：`run_id`、`node_id`、`stream`（stdout/stderr）、`lines`
  - 输出：日志片段

## AI 手写 YAML 的闭环流程

### 1) 生成前：收集节点信息

1. AI 调用 `nodehub.list_packages` 获取可用节点包。
2. 对候选包调用 `nodehub.get_manifest`，得到端口与参数 schema。

### 2) 生成：构造 `runtime.yaml`

AI 生成满足解析器约束的 YAML（关键约束示例）：

- 顶层字段：`graph_id`、`graph_version`（可选）、`node_hub_path`（可选）、`nodes`、`edges`、`restart_policy`（可选）
- `nodes[*]`：`id`、`package`、`params`（可选）、`entrypoint`（可选覆盖）
- `edges[*]`：
  - `from`: `"<from_node>.<from_port>"`
  - `to`: `"<to_node>.<to_port>"`

### 3) 校验：结构化反馈驱动修正

1. 调用 `yaml.validate_runtime`。
2. 若失败，AI 根据 `errors/warnings` 精确修正（例如端口名拼写、类型不兼容、缺失节点包、循环依赖）。
3. 调用 `graph.plan_startup_layers` 做一次“可解释确认”（启动层级是否符合预期）。

### 4) 运行验证（可选）

1. 调用 `diagnostics.run`，确保“解析→扫描→注册→图校验→拓扑→socket 路径”全链路 OK。
2. 若开启运行模式，再调用 `runtime.start` 短时启动并 `runtime.tail_logs` 获取关键节点日志。
3. AI 根据日志与状态，再回到第 2) 步修正 YAML/参数。

## 结果数据格式建议

为了让 AI 能“稳定地自动修复”，建议所有校验/诊断接口输出结构化字段，而不是仅返回文本：

- 错误要包含：`category`（parse/config/graph/topology/runtime）、`message`、`location`（尽量带 `node_id`、`port`、`edge_index` 等定位信息）。
- 对于“端口不存在”这类错误，返回 `available_ports` 作为修复提示。
- 对于“类型不兼容”，返回两端类型与建议替代端口（如有）。

## 安全与约束

即便是本机开发场景，MCP 仍需做硬约束，避免误用与被动风险：

- **路径约束**：所有文件访问限定在项目根目录之内；`hub_path` 只能指向允许的 `node-hub/`。
- **拒绝路径穿越**：对 `package` 做规范化并禁止 `..` 等危险片段。
- **执行白名单**：只允许执行固定脚本/固定模块（如 `tools/run_tests.sh`、`runtime.main`），禁止任意命令。
- **超时与截断**：诊断/测试/启动均设置最大耗时；stdout/stderr 按行数或字节截断。
- **最小权限默认**：默认运行在“只读/静态模式”，执行模式需要显式开启。
- **敏感信息处理**：输出中避免回显环境变量全量内容；对潜在密钥做简单脱敏（如匹配常见 token 形式）。

## 里程碑建议

### MVP（1 天内可打通闭环）

- `nodehub.list_packages` / `nodehub.get_manifest`
- `yaml.validate_runtime`（组合解析 + 校验 + 拓扑）
- `graph.plan_startup_layers`

这已经足够支持 AI 生成可运行的 YAML，并能自我修正。

### Phase 2（调试执行）

- `diagnostics.run`（结构化步骤输出）
- `tests.run`（受控执行 + 报告路径返回）

### Phase 3（运行时管理）

- `runtime.start/status/stop` + `runtime.tail_logs`
- 运行态节点状态结构化（PID、退出码、重启次数、健康检查结果）

## 风险与注意事项

- **长进程管理复杂度**：runtime 启动后会派生多个节点进程；需要稳定的 `run_id`、日志目录与回收策略。
- **输出一致性**：如果依赖脚本 stdout 做解析，易受格式变化影响；优先模块化调用得到 dict 结果。
- **版本漂移**：YAML 结构与校验规则会演进，建议接口输出中带 `schema_version`，并在 MCP 层做向后兼容策略。

