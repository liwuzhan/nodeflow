# 机器人节点化框架 PRD v0.1（配置驱动 / 最新值数据流 / Web 蓝图）

## 1. Product Overview

### 1.1 背景与问题
目标场景为低速车辆（如拖拉机/农机）上的边缘计算设备。车辆的行为策略强依赖后方挂载机具，更换机具意味着行为模式与数据链路变化。现有框架在更换 YAML 后可能涉及重新编译或开发体验不匹配边缘设备使用方式。

### 1.2 产品定义
本产品是一套配置驱动的本机节点编排框架，通过一份运行配置（YAML 或等价格式）决定：
- 从 `node-hub/` 中拉起哪些节点（Python 脚本、Shell、Bat、已编译二进制等）
- 节点之间端口的连接关系（数据流拓扑）
- 节点运行参数（透传给节点，由节点自行解释与使用）

同时提供一个 Web 蓝图编辑器（v1 仅生成 YAML）：
- 读取节点包自带的“节点说明书 YAML”（描述端口、类型、参数）
- 画布拖拽、连线、配置参数
- 导出“运行 YAML”
- 保存“工程文件”（包含 UI 布局等，运行时不需要）

### 1.3 核心原则
- 停机切换：更换机具=停止状态，切换运行 YAML 后重启框架。
- 节点自治：节点启动失败/内部异常优先视为节点问题；框架层仅做编排与最基本的状态上报。
- 最小外部性：框架不引入通用消息队列语义；默认数据通道只保留最新值（latest-value）。
- 实时性优先：数据完整性、回放、持久化不由框架保证；如需队列（如日志/录包）由节点自行实现。
- 本机优先：默认假设节点都在同一台机器上运行；如需外部网络连接由节点自行使用端口通信，框架不限制。

### 1.4 目标用户
- 方案/算法工程师：组合策略、部署到车端、快速换机具/换方案。
- 现场调试人员：按计划选择配置并启动，观察最基础的"哪些节点在跑"。

### 1.5 技术决策（v0.1 定案）

#### 1.5.1 节点间数据流（IPC）
- **机制**：采用进程间通信（Unix Domain Socket / Named Pipe），每个端口连接作为一个数据通道。
- **语义**：每个通道仅保留最新值（latest-value），读取时返回当前可用的最新数据，无数据时返回空。
- **格式**：数据以 JSON 序列化传输（带宽需求有限，内存性能充足，不需优化）。
- **阻塞模型**：非阻塞读取；节点自行决定等待策略（轮询/超时/事件驱动）。
- **封包格式**（v0.1 定案）：
  - 4 字节小端序整数（消息体长度）+ JSON 消息体
  - 例如：`[0x0F, 0x00, 0x00, 0x00]` + `{"data":"value"}`（15字节JSON）
- **最新值实现**：
  - 框架仅负责建立 Socket 连接，不实现最新值语义。
  - 最新值由**接收端节点 SDK** 负责实现：循环读取 Socket 清空缓冲区，仅保留最后一条消息。
  - 发送端节点正常写入即可，无需关心接收端是否读取。

#### 1.5.2 节点参数与连接传递
框架通过以下方式将运行 YAML 中的参数和 Socket 连接信息传递给节点：

**命令行参数**：通过 `--params` 参数传递 JSON 格式的参数对象。
- 示例：`python3 run.py --params '{"device":"/dev/ttyUSB0","baudrate":115200}'`

**环境变量**（框架自动注入）：
| 环境变量 | 说明 | 例子 |
|---|---|---|
| `NODE_ID` | 节点实例 ID | `rtk_main` |
| `NODE_HUB_PATH` | 节点库根目录 | `/app/node-hub` |
| `NODE_IN_<PORT_NAME>` | 输入端口 Socket 路径 | `NODE_IN_gps_cfg=/tmp/nodeflow_rtk_main.gps_cfg.in` |
| `NODE_OUT_<PORT_NAME>` | 输出端口 Socket 路径 | `NODE_OUT_gps_fix=/tmp/nodeflow_rtk_main.gps_fix.out` |
| `NODE_SOCKET_DIR` | 所有 Socket 文件的临时目录 | `/tmp/nodeflow_sockets` |

**约定**：
- 节点启动后应立即尝试连接所有输入端口（通过 `NODE_IN_*` 环境变量获得 Socket 路径）。
- 节点启动后应立即创建所有输出端口的 Socket 监听器（通过 `NODE_OUT_*` 环境变量指定的路径）。
- 框架不强制节点如何使用参数，仅保证按上述约定传递。

#### 1.5.3 节点启动顺序
- **拓扑排序**：框架根据 `edges` 列表分析数据依赖关系，按拓扑顺序启动节点。
  - 例如：`A.output → B.input` 则 A 必须先于 B 启动。
- **并行启动**：无数据依赖的节点可并行启动（如多个独立数据源）。
- **启动超时**：节点启动后需在规定时间内完成初始化（v0.1 建议 30s），否则视为启动失败。

## 2. Objectives & Success Metrics

### 2.1 目标
- O1：支持通过运行 YAML 实现“换机具=换拓扑+换参数+重启即生效”。
- O2：节点说明书 YAML 作为节点包的一部分，使节点“可发现、可连线、可配置”。
- O3：提供 Web 蓝图工具，实现“可视化拼图→导出运行 YAML”，v1 不要求一键运行。

### 2.2 成功指标
- M1：从打开 Web 编辑器到导出运行 YAML 的时间 ≤ 10 分钟（熟练用户）。
- M2：新增一个节点包到 `node-hub/` 后，Web 编辑器可自动识别（无需改框架代码）。
- M3：方案切换（替换运行 YAML + 重启）可在 ≤ 2 分钟内完成（含人工复制 YAML）。

## 3. User Stories

### 3.1 计划先行（策略→换机具→上车）
- 作为方案人员，我先在电脑上用 Web 蓝图选择“播种策略”的节点组合与参数，导出运行 YAML。
- 我到现场换上播种机具，把运行 YAML 复制到车端指定路径，双击启动框架即可按新拓扑运行。

### 3.2 多实例节点
- 作为方案人员，我需要在同一拓扑里放两个同类节点实例（如两个不同来源的定位输入），并把它们连到不同的下游。

### 3.3 节点包自描述
- 作为节点开发者，我把 `node-hub/rtk/node.yaml` 与 `run.py`（或可执行文件）放在同目录。
- Web 蓝图能展示该节点的输入输出端口与类型，用户能配置参数并连线。

## 4. Functional Requirements

### 4.1 节点仓库与发现（Node Hub）
- FR-1：框架支持配置 `node-hub` 根目录（默认 `./node-hub/`）。
- FR-2：每个节点包位于 `node-hub/<node_name>/`。
- FR-3：节点说明书文件命名统一为 `node.yaml`（v0.1 定案）。
- FR-4：Web 编辑器读取 `node-hub/` 下所有节点说明书，形成“节点库”。

建议目录结构：
- `node-hub/rtk/node.yaml`
- `node-hub/rtk/run.py` 或 `node-hub/rtk/rtk` 或 `node-hub/rtk/run.sh` 或 `node-hub/rtk/run.bat`

### 4.2 运行配置（Runtime YAML）
- FR-5：运行 YAML 定义一个“图”（graph）：节点实例列表 + 连接关系列表 + 全局设置（可选）。
- FR-6：支持同一节点包多实例（每个实例有唯一 `id`）。
- FR-7：运行 YAML 中的节点参数作为透传配置：框架负责把参数交给节点，不要求框架理解参数语义。
- FR-8：更换运行 YAML 的生效方式为：停止框架 → 替换 YAML → 启动框架。

### 4.3 节点启动（EntryPoint）
- FR-9：节点说明书 YAML 中必须声明启动入口，可按 OS 区分。
- FR-10：节点拉起失败视为节点问题；框架至少能标记该节点为 `failed_to_start` 并记录一次错误信息（退出码/命令不可执行）。
- FR-11：节点运行中崩溃时，框架按策略自动重启 N 次；超过阈值则停掉该节点并将图标记为异常。
- FR-11a：框架按拓扑顺序启动节点（根据 edges 分析依赖），无依赖的节点可并行启动。
- FR-11b：框架通过命令行参数 `--params` 传递 JSON 格式的参数给节点，并注入环境变量（如 `NODE_ID`）。

### 4.4 端口与连线（Ports & Edges）
- FR-12：节点说明书定义输入/输出端口列表；端口可选声明 `type`，不声明则视为 `any`。
- FR-13：Web 编辑器连线规则（严格模式）：
  - `type: any` 的端口可连接任何类型。
  - 非 `any` 类型的端口仅允许同类型相连（编辑器禁止非同类型的连线）。
  - 例外：某些特殊节点（如日志聚合节点）可声明输入 `type: any` 来接收来自任何节点的数据。
- FR-14：运行时每个端口只保留最新值（latest-value），不提供队列语义。

### 4.5 Web 蓝图编辑器（v1：仅生成 YAML）
- FR-15：Web 编辑器提供：节点库、画布拖拽、多实例、端口连线、参数编辑、导出运行 YAML、保存工程文件。
- FR-16：v1 不包含“一键运行/停止/日志查看”。

### 4.6 工程文件 vs 运行文件（必须区分）
- FR-17：工程文件包含 UI 信息：节点坐标、缩放、注释、分组等。
- FR-18：运行 YAML 不包含 UI 信息，仅含运行必需字段。

## 5. Non-Functional Requirements

- NFR-1（平台）：v1 以 Linux 为主；允许在 WSL 开发与验证。
- NFR-2（资源）：不设强约束；资源耗尽不作为 v1 阻塞项。
- NFR-3（可靠性）：节点崩溃可重启，超过阈值停机。
- NFR-4（启动协调）：框架根据数据流依赖关系（edges）自动计算启动顺序（拓扑排序），无依赖节点并行启动。
- NFR-5（可扩展）：未来可加运行控制台、远程分发、录包回放，但不影响 v1 规范。

## 6. User Experience（Web 蓝图）

### 6.1 关键流程（v1）
1. 用户打开 Web 编辑器
2. 编辑器扫描并加载 `node-hub/` 下所有 `node.yaml`
3. 用户拖拽节点到画布，形成多个实例（自动生成 `id`，可改名）
4. 用户从输出端口拖线到输入端口
5. 用户填写参数（键值；如有类型则做基础校验）
6. 用户保存工程文件（用于下次继续编辑）
7. 用户导出运行 YAML（拷贝到车端指定目录）
8. 用户在车端双击启动框架（框架读取运行 YAML 拉起节点）

### 6.2 校验与提示（v1 建议）
- 未连入的输入端口：提示但允许导出
- 类型不匹配：提示；默认允许导出
- 重名实例 ID：禁止导出
- 引用不存在的节点包：禁止导出

## 7. YAML 规范（v0.1）

### 7.1 节点说明书 YAML（Node Manifest）

#### 7.1.1 设计目标
- 节点“可发现”：可被 Web 编辑器扫描到
- 节点“可启动”：声明如何启动
- 节点“可连线”：声明端口
- 节点“可配置”：声明参数（可选类型）

#### 7.1.2 文件位置
- 路径：`node-hub/<node_name>/node.yaml`

#### 7.1.2a 参数与连接传递约定

**命令行参数**：
- 框架启动节点时，会自动在命令后追加 `--params '<json_object>'` 参数
- 例如：`python3 run.py --params '{"device":"/dev/ttyUSB0"}'`
- 节点需自行解析 `--params` 参数并从中提取配置

**环境变量**（框架自动注入）：
- `NODE_ID`：节点实例 ID
- `NODE_HUB_PATH`：节点库根目录
- `NODE_SOCKET_DIR`：所有 Socket 的临时目录
- `NODE_IN_<PORT_NAME>`：输入端口 Socket 路径（对应每个输入端口）
- `NODE_OUT_<PORT_NAME>`：输出端口 Socket 路径（对应每个输出端口）

**节点启动行为**：
- 节点启动后应立即尝试连接所有输入端口（从 `NODE_IN_*` 环境变量获取 Socket 路径）
- 节点启动后应立即创建所有输出端口的 Socket 监听器（通过 `NODE_OUT_*` 环境变量指定的路径）
- 数据读取应使用非阻塞模式，实现最新值语义需由节点 SDK 循环读取清空缓冲区

#### 7.1.3 字段定义
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `name` | string | 是 | 无 | 节点名，建议与目录名一致 |
| `version` | string | 否 | `0.1.0` | 节点包版本 |
| `description` | string | 否 | 空 | 一句话说明 |
| `entrypoints` | object | 是 | 无 | 按平台声明启动命令 |
| `ports.inputs` | list | 否 | 空列表 | 输入端口定义 |
| `ports.outputs` | list | 否 | 空列表 | 输出端口定义 |
| `params` | object | 否 | 空对象 | 参数 schema，仅用于编辑器提示/校验 |

`entrypoints`：
| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `linux.kind` | string | 是 | `python`/`sh`/`binary` 等（仅枚举建议，不强制） |
| `linux.cmd` | list[string] | 是 | 启动命令与参数数组 |
| `windows.kind` | string | 否 | `bat` 等 |
| `windows.cmd` | list[string] | 否 | 启动命令与参数数组 |

端口定义：
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `name` | string | 是 | 无 | 端口名 |
| `type` | string | 否 | `any` | 端口类型，用于连线校验 |

参数定义（建议但不强制）：
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `type` | string | 否 | `any` | `string/int/float/bool/any` |
| `required` | bool | 否 | `false` | 是否必填 |
| `default` | any | 否 | 无 | 默认值 |

#### 7.1.4 示例
```yaml
name: rtk
version: 0.1.0
description: RTK定位输入节点

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

ports:
  inputs:
    - name: ntrip_cfg
      type: any
  outputs:
    - name: gps_fix
      type: gps.fix

params:
  device:
    type: string
    required: true
  baudrate:
    type: int
    default: 115200
```

### 7.2 运行 YAML（Runtime Graph）

#### 7.2.1 文件位置（建议）
- v0.1 不强制，但建议约定为：`./runtime/runtime.yaml`

#### 7.2.2 字段定义
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `graph_id` | string | 是 | 无 | 图 ID，例如 `seeding_plan_a` |
| `graph_version` | int | 否 | 1 | 图版本 |
| `node_hub_path` | string | 否 | `./node-hub` | 节点库路径 |
| `nodes` | list | 是 | 无 | 节点实例列表 |
| `edges` | list | 是 | 空列表 | 连接关系列表 |
| `restart_policy` | object | 否 | 默认策略 | 崩溃重启策略 |

`nodes[]`：
| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | string | 是 | 实例 ID，必须唯一 |
| `package` | string | 是 | 节点包名，对应 `node-hub/<package>/` |
| `entrypoint` | object | 否 | 覆盖 manifest 默认入口（可选） |
| `params` | object | 否 | 透传参数，节点自行解释 |

`edges[]`：
| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `from` | string | 是 | 形如 `<node_id>.<port>` |
| `to` | string | 是 | 形如 `<node_id>.<port>` |
| `type` | string | 否 | 导出时可写入，便于审阅 |

`restart_policy`：
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `max_retries` | int | 否 | 3 | 最大重启次数 |
| `backoff_ms` | int | 否 | 500 | 重启退避 |

#### 7.2.3 示例
```yaml
graph_id: seeding_plan_a
graph_version: 1

nodes:
  - id: rtk_main
    package: rtk
    params:
      device: "/dev/ttyUSB0"
      baudrate: 115200

  - id: controller
    package: seed_controller
    params:
      vehicle_type: "tracked"

edges:
  - from: rtk_main.gps_fix
    to: controller.gps_fix
    type: gps.fix

restart_policy:
  max_retries: 3
  backoff_ms: 500
```

### 7.3 工程文件（Project File）v0.1

#### 7.3.1 目标
保存蓝图 UI 状态，不影响运行配置；用于"继续编辑"。

#### 7.3.2 文件格式与位置
- **格式**：JSON（v0.1 冻结）
- **命名约定**：`<project_name>.nodeflow.json`
- 工程文件与运行 YAML 保存在不同位置，Web 编辑器加载工程文件后可导出运行 YAML

#### 7.3.3 字段定义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `project_id` | string | 是 | 项目唯一标识 |
| `project_name` | string | 是 | 项目名称（用于显示） |
| `created_at` | string | 否 | 创建时间（ISO 8601） |
| `updated_at` | string | 否 | 最后修改时间（ISO 8601） |
| `node_hub_path` | string | 否 | 节点库路径（默认 `./node-hub`） |
| `canvas` | object | 否 | 画布视图状态 |
| `nodes_ui` | list | 否 | 各节点的 UI 信息 |
| `runtime_graph` | object | 是 | 内嵌的运行 YAML 内容（与运行 YAML 结构一致） |

`canvas`：
| 字段 | 类型 | 说明 |
|---|---|---|
| `zoom` | number | 缩放级别（默认 1.0） |
| `pan_x` | number | 水平偏移 |
| `pan_y` | number | 竖直偏移 |

`nodes_ui[]`：
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 节点实例 ID（对应 runtime_graph.nodes[].id） |
| `x` | number | 画布坐标 X |
| `y` | number | 画布坐标 Y |
| `color` | string | 颜色（可选） |
| `group` | string | 分组名（可选） |
| `comment` | string | 注释（可选） |

#### 7.3.4 示例
```json
{
  "project_id": "seeding_plan_a_v1",
  "project_name": "播种方案 A",
  "created_at": "2024-12-18T10:00:00Z",
  "updated_at": "2024-12-18T15:30:00Z",
  "node_hub_path": "./node-hub",
  "canvas": {
    "zoom": 1.2,
    "pan_x": 100,
    "pan_y": -50
  },
  "nodes_ui": [
    {
      "id": "rtk_main",
      "x": 50,
      "y": 100,
      "color": "#FF6B6B",
      "group": "输入源",
      "comment": "主定位信号"
    },
    {
      "id": "controller",
      "x": 300,
      "y": 100,
      "color": "#4ECDC4",
      "group": "控制层"
    }
  ],
  "runtime_graph": {
    "graph_id": "seeding_plan_a",
    "graph_version": 1,
    "nodes": [
      {
        "id": "rtk_main",
        "package": "rtk",
        "params": {
          "device": "/dev/ttyUSB0",
          "baudrate": 115200
        }
      },
      {
        "id": "controller",
        "package": "seed_controller",
        "params": {
          "vehicle_type": "tracked"
        }
      }
    ],
    "edges": [
      {
        "from": "rtk_main.gps_fix",
        "to": "controller.gps_fix",
        "type": "gps.fix"
      }
    ]
  }
}
```

## 8. 故障与恢复（v0.1 最小集合）

### 8.1 框架层错误类型
- `node_not_found`：节点包不存在
- `manifest_invalid`：`node.yaml` 不合法
- `failed_to_start`：入口命令无法执行或启动即退出
- `node_crashed`：运行中退出（带退出码）

### 8.2 重启策略
- 默认自动重启，超过次数停掉节点并将整体状态标记为异常。

## 9. 里程碑建议

### Phase 0：规范冻结
- 冻结 `node.yaml` v0.1 字段
- 冻结 runtime YAML v0.1 字段
- 明确工程文件与运行文件导出规则

### Phase 1：Web 蓝图 v1
- 扫描 `node-hub/` 节点库
- 画布拖拽、连线、参数编辑
- 保存工程文件、导出运行 YAML

### Phase 2：运行时编排 v1
- 读取运行 YAML
- 拉起节点、建立端口数据通道（latest-value）
- 崩溃重启策略与最小状态输出

## 10. v0.1 定案与约束（汇总）

### 10.1 文件与目录约定
- 节点说明书文件名：`node.yaml`
- 节点包位置：`node-hub/<node_name>/`
- 工程文件格式：JSON（`<project_name>.nodeflow.json`）
- 运行文件格式：YAML（`runtime.yaml`）

### 10.2 运行语义
- **切换方式**：停机切换运行 YAML 后重启框架
- **数据语义**：每端口 latest-value；无数据即为空，由节点自处理
- **启动顺序**：拓扑排序，按数据流依赖关系启动节点

### 10.3 节点间通信（IPC）
- **机制**：Unix Domain Socket（Linux）/ Named Pipe（Windows）
- **数据格式**：JSON 序列化
- **阻塞模型**：非阻塞读取
- **封包格式**：4 字节小端序长度 + JSON 消息体
- **最新值语义**：由接收端节点 SDK 实现（循环读取清空缓冲区），框架只负责连接建立

### 10.4 参数与连接传递
- **命令行参数**：`--params '{"key":"value"}'`（JSON 格式）
- **环境变量**：框架注入
  - `NODE_ID`、`NODE_HUB_PATH`、`NODE_SOCKET_DIR`（通用）
  - `NODE_IN_<PORT_NAME>`、`NODE_OUT_<PORT_NAME>`（端口特定 Socket 路径）
- **约定**：节点启动后立即连接输入端口、创建输出端口监听器

### 10.5 类型系统
- **严格校验**：非 `any` 类型仅允许同类型连接
- **例外**：`type: any` 可连接任何类型（如日志聚合节点）

### 10.6 前端范围
- v1 只负责生成运行 YAML 与保存工程文件（JSON）
- 不包含一键运行/停止/日志查看功能
