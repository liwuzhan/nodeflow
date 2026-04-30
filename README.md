# NodeFlow - 机器人节点编排框架

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type Checked](https://img.shields.io/badge/type%20checked-mypy-informational)](http://mypy-lang.org/)

配置驱动的节点编排框架，专为低速车辆边缘计算场景设计。通过声明式 YAML 配置实现节点间数据流编排，支持 AI 辅助的调试和运维能力（MCP 服务）。

---

## ✨ 核心特性

- 🎯 **声明式配置**: 通过 YAML 定义节点拓扑和数据流，无需编写管道代码
- 🔌 **节点化架构**: 进程隔离的节点设计，独立开发、测试和部署
- 🚀 **混合 IPC 架构**: 基于 SharedBuffer + ZeroMQ 的高性能进程间通信，解决传统 Socket 的数据丢失问题
- 📦 **灵活缓冲区配置**: 支持按需配置输出端口缓冲区大小，适应各类传感器（RTK/IMU 默认 1MB，LiDAR/4K 相机可配置 5-50MB+）
- 🧠 **AI 辅助调试**: 集成 MCP (Model Context Protocol) 服务，支持智能故障诊断
- 📊 **拓扑分析**: 自动检测循环依赖、端口类型匹配和启动顺序优化
- 🛡️ **安全加固**: 路径边界验证、参数类型检查、异常隔离机制
- 📜 **数据契约**: 基于 Pydantic 的 Schema 定义，支持离线合规性检查（Health Check）
- 🧪 **完善测试**: 单元测试、集成测试、Mock 节点覆盖

---

## 📋 系统要求

- **Python**: 3.12 或更高版本
- **操作系统**: Linux / macOS (Unix Domain Socket 支持)
- **依赖**: 见 `requirements.txt`

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone <repository-url>
cd robot-nodeflow

# 安装依赖
pip install -r requirements.txt

# 或安装为可编辑包（推荐开发者）
pip install -e .
```

### 2. 验证安装

```bash
# 运行单元测试
pytest tests/unit/

# 运行路径安全测试
python3 tests/mcp/test_error_responses.py

# 代码质量检查
python3 -m black --check mcp_server.py runtime_manager.py
python3 -m mypy --ignore-missing-imports mcp_server.py runtime_manager.py
```

### 3. 运行示例

```bash
# 完整仿真场景（推荐）
python3 -m runtime.main examples/planning_simulation.yaml

# 查看可用节点
python3 -m tools.cli.core.cli node list

# 查看节点日志
nodeflow logs --follow
```

---

## 🏗️ 项目结构

```
node/
├── runtime/              # 运行时框架核心
│   ├── config/           # 配置解析
│   ├── graph/            # 图拓扑分析
│   ├── orchestrator/     # 节点编排与生命周期
│   ├── monitoring/       # 进程监控与自动重启
│   ├── task/             # 任务下发与执行
│   └── utils/            # 工具函数
│
├── sdk/                  # 节点开发 SDK
│   ├── doc/              # SDK 文档
│   ├── test_utils/       # 测试工具
│   └── utils/            # 地理坐标等工具
│
├── node-hub/             # 节点库
│   ├── coord_transform/  # 坐标转换网关
│   ├── global_coverage/  # 全局覆盖规划
│   ├── waypoint_selector/# 前瞻点选择
│   ├── track_controller/ # 轨迹跟踪控制
│   ├── sim_output/       # 仿真器输出
│   ├── sim_input/        # 仿真器输入
│   └── ...               # 更多节点
│
├── simulator/            # 农田仿真器
│   └── docs/             # 仿真器文档
│
├── web-editor/           # Web 可视化编辑器
│   └── docs/             # 编辑器文档
│
├── tools/cli/            # 命令行工具
│   └── commands/         # CLI 命令
│
├── tests/                # 测试套件
│   ├── unit/             # 单元测试
│   └── integration/      # 集成测试
│
├── docs/                 # 文档
│   ├── old/              # 历史文档归档
│   ├── 评审报告/          # AI 评审报告
│   └── CHANGELOG.md      # 更新日志
│
├── mcp_server.py         # MCP 服务 (AI 辅助调试)
├── runtime_manager.py    # 运行时进程管理
└── pytest.ini            # 测试配置
```

---

## 🧩 核心概念

### 节点（Node）
独立运行的进程单元，通过定义良好的端口（Ports）与其他节点交换数据。

**特点**:
- 进程隔离，故障不传播
- 支持热重启和独立升级
- 通过 `node.yaml` 声明接口

**示例**: GPS 传感器节点、路径规划节点、电机控制节点

### 运行配置（Runtime YAML）
声明式配置文件，定义：
- 节点实例及其参数
- 节点间的连接关系（数据流）
- 启动顺序和依赖关系

**示例**:
```yaml
graph_id: "sensor_fusion_demo"
graph_version: "1.0.0"
node_hub_path: "./node-hub"

nodes:
  - id: gps_sensor
    package: sim_gps
    params:
      frequency: 10

  - id: imu_sensor
    package: sim_imu
    params:
      frequency: 100

  - id: fusion
    package: sensor_fusion
    params:
      algorithm: "kalman_filter"

edges:
  - from: gps_sensor.position
    to: fusion.gps_input
  - from: imu_sensor.orientation
    to: fusion.imu_input
```

### 节点说明书（Node Manifest）
每个节点包必须包含的 `node.yaml`，描述：
- 输入/输出端口及其类型
- 可配置参数及默认值
- 启动入口点（Python 模块路径）

**示例**:
```yaml
name: "sim_gps"
version: "1.0.0"
description: "GPS 传感器模拟器"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

ports:
  outputs:
    - name: position
      type: sensor.gps
      description: GPS 坐标 (lat, lon, alt)
      buffer_size: 1048576  # 1MB (可选，默认值)
      conflate: true        # Latest-value 模式 (可选，默认值)

params:
  frequency:
    type: int
    default: 10
    description: "数据发布频率 (Hz)"
```

### IPC 通信机制
基于 **混合架构 (SharedBuffer + ZeroMQ)** 的高性能进程间通信，解决传统 Socket 的 Slow Joiner 问题。

**核心设计**:
- 📦 **SharedBuffer (mmap)**: 持久化数据存储，确保后启动的节点也能读取历史数据
- 🔔 **ZeroMQ PUB/SUB**: 实时事件通知，减少轮询开销
- 🔄 **Latest-Value 语义**: 读取总是获取最新值（覆盖模式）
- ⚡ **JSON 序列化**: 简单高效，支持复杂数据结构

**优势**:
- ✅ **无数据丢失**: 数据持久在共享内存，不受节点启动顺序影响
- ✅ **低延迟**: 内存访问 + ZeroMQ 通知，毫秒级延迟
- ✅ **可配置缓冲区**: 支持 1MB (默认) 到 50MB+ 的灵活配置
- ✅ **简化连接管理**: 无需重连逻辑，缓冲区由 Runtime 预分配

**缓冲区配置**:
```yaml
# 在 node.yaml 中配置输出端口缓冲区
outputs:
  - name: point_cloud
    type: sensor.lidar
    buffer_size: 5242880  # 5MB for multi-line LiDAR
    conflate: true        # Latest-value mode (default)
```

**Buffer 大小参考**:
| 数据类型 | 推荐大小 |
|---------|---------|
| RTK/IMU | 1MB (默认) |
| 路径规划 | 1MB (默认) |
| 多线激光雷达 | 5-10MB |
| 4K 摄像头 | 30-50MB |

#### 路径与地址约定（2025-12 更新）
- 统一临时目录根: `/tmp/nodeflow`，子目录：
  - 缓冲区: `/tmp/nodeflow/buffers`
  - 日志: `/tmp/nodeflow/logs`
- ZeroMQ 地址规范: `ipc:///tmp/nodeflow/<node_id>.<port_name>`
- 运行时与SDK通过常量管理上述路径，示例见 `runtime/utils/constants.py`

#### 弃用说明
- 旧版 Unix Socket/MsgPack 通道与相关工具（SocketManager、protocol/channel）已不在运行路径中使用
- SDK 中 `latest_value_reader` 不再依赖旧协议，建议使用 `InputPort.recv_latest()` 的混合方案

---

## 📡 任务下发与云端对接

NodeFlow 提供完整的任务下发与生命周期管理系统，支持**离线单机**和**云端对接**两种模式。

### 核心概念

**任务 = 预设 YAML + 参数覆盖**。无需为每个任务编写新的配置文件，只需选择预设配置并覆盖节点参数即可。

### 离线模式（单机）

```bash
# 1. 启动 daemon，加载预设配置
nodeflow runtime start examples/tillage_operation.yaml --daemon

# 2. 下发任务（YAML 定义地块+参数覆盖）
nodeflow task run examples/tillage_task.yaml

# 3. 查看任务列表
nodeflow task list
nodeflow task show <task_id>

# 4. 取消任务
nodeflow task cancel <task_id>
```

**任务 YAML 示例** (`examples/tillage_task.yaml`):
```yaml
task_id: "local-tillage-001"
preset_yaml: "tillage_operation"
operation_type: "tillage"
node_params:
  parcel_planner:
    parcel_name: "demo_field"
  trajectory_loader:
    trajectory_file: ""
```

### 云端对接

端侧通过 **MQTT + HTTP** 与云端通信:

| 方向 | 协议 | 用途 |
|------|------|------|
| 云端→端侧 | MQTT QoS 1 | 任务下发、取消 |
| 端侧→云端 | MQTT QoS 0 | 状态上报、心跳（30s 间隔） |
| 端侧→云端 | MQTT QoS 1 | 任务接收确认（ACK） |
| 端侧→云端 | HTTP GET | 大文件下载（地块/路径，可达 10MB） |

### CLI 命令

| 命令 | 用途 |
|------|------|
| `nodeflow task run <file>` | 执行本地任务文件 |
| `nodeflow task list` | 列出所有任务及状态 |
| `nodeflow task show <id>` | 查看任务详情 |
| `nodeflow task cancel <id>` | 取消执行中/等待中的任务 |

### 系统架构

```
┌── 云端 ──────────────────────────────────────────┐
│  Job Manager → Splitter → Dispatch → HTTP Server  │
└────────────────┬─────────────────────────────────┘
                 │ MQTT + HTTP
┌── 端侧 ───────┼─────────────────────────────────┐
│  Task Agent   │ (MQTT Sub + HTTP Client)          │
│  TaskExecutor → Runtime Daemon (参数注入)         │
│  TaskStore    (JSON 持久化, 状态恢复)             │
└──────────────────────────────────────────────────┘
```

**详细文档**:
- 📖 [云端集成对接文档](docs/CLOUD_INTEGRATION.md) — MQTT 协议、HTTP API、消息格式规范
- 📖 [Daemon 模式指南](docs/DAEMON_MODE_GUIDE.md) — 守护进程运行模式

---

## 🧠 MCP 服务（AI 辅助调试）

NodeFlow 集成了 **Model Context Protocol (MCP)** 服务，支持通过 AI（如 Claude Desktop）进行智能运维和故障诊断。

### 功能列表

| 工具 | 功能 | 用途 |
|------|------|------|
| `nodeflow/get-node-info` | 查询节点库信息 | 列出可用节点、查看节点接口 |
| `nodeflow/validate-yaml` | 验证 YAML 配置 | 检测配置错误、端口类型不匹配 |
| `nodeflow/edit-yaml` | 修改 YAML 配置 | 动态调整节点参数 |
| `nodeflow/run-runtime` | 启动运行时 | 启动节点数据流 |
| `nodeflow/stop-runtime` | 停止运行时 | 优雅关闭所有节点 |
| `nodeflow/read-logs` | 读取节点日志 | 故障诊断、性能分析 |
| `nodeflow/get-runtime-status` | 获取运行状态 | 监控节点健康度 |

### 安全机制

✅ **路径边界验证**: 所有文件操作限制在项目根目录内，防止路径穿越攻击
✅ **参数类型检查**: 严格的输入验证，防止注入攻击
✅ **进程隔离**: 运行时故障不影响 MCP 服务
✅ **审计日志**: 完整的操作记录和错误追踪

**详细说明**: 见 [MCP 服务修复报告](docs/MCP_SERVICE_FIX_REPORT.md)

### 启动 MCP 服务

```bash
# 启动 MCP 服务器
python3 mcp_server.py

# 在 Claude Desktop 中配置
# 路径: ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "nodeflow": {
      "command": "python3",
      "args": ["/path/to/node/mcp_server.py"]
    }
  }
}
```

---

## 🧪 测试

### 运行测试套件

```bash
# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# MCP 服务测试
python3 tests/mcp/test_error_responses.py
python3 tests/mcp/test_mcp_functionality.py

# 覆盖率报告
pytest --cov=runtime --cov=sdk --cov-report=html
```

### 测试覆盖

- ✅ 配置解析和验证 (YAML Parser, Config Validator)
- ✅ 图拓扑分析 (循环检测, 启动排序)
- ✅ IPC 通信 (Socket 创建, 消息序列化)
- ✅ MCP 服务 (路径安全, 错误响应格式)
- ✅ Mock 节点 (10 个测试节点, 7 种场景)

### 为你的节点添加测试

NodeFlow提供完整的节点测试框架，包括SDK测试工具库和模板：

```bash
# 快速开始：复制测试模板到你的节点
cp -r .test_template node-hub/your_node/test

# 修改模板中的TODO项并运行测试
cd node-hub/your_node
python -m pytest test/ -v
```

**测试框架特性**:
- 🔧 **MockSDK工具**: 无需真实SDK的隔离测试环境
- 📋 **pytest Fixtures**: 预配置的测试数据和临时目录管理
- 📦 **测试模板**: 单元测试和集成测试的完整模板
- 📚 **测试常量**: 常用地理坐标和数据结构示例

**详细指南**:
- 📖 [5分钟快速开始](docs/TESTING_QUICKSTART.md) - 快速为节点添加测试
- 📖 [完整测试指南](docs/NODE_TESTING_GUIDE.md) - 测试范式和最佳实践
- 💡 参考实现: `node-hub/trajectory_viz/test/` (34个测试)

---

## 📚 文档

### 核心文档

| 文档 | 描述 |
|------|------|
| [项目综述](docs/PROJECT_OVERVIEW_20260102.md) | 项目全面介绍，AI 驱动开发总结 ⭐ |
| [更新日志](docs/CHANGELOG.md) | 完整的版本变更记录 |
| [SDK 快速入门](sdk/doc/SDK_GETTING_STARTED.md) | 10 分钟上手 NodeFlow SDK |
| [SDK API 参考](sdk/doc/SDK_API_REFERENCE.md) | 完整的 SDK API 文档 |
| [SDK 最佳实践](sdk/doc/SDK_BEST_PRACTICES.md) | 架构设计、性能优化 |
| [节点开发规范](node-hub/doc/节点开发规范.md) | 节点开发标准和最佳实践 |

### 功能文档

| 文档 | 描述 |
|------|------|
| [云端集成对接文档](docs/CLOUD_INTEGRATION.md) | MQTT 协议、HTTP API、消息格式规范 ⭐ |
| [结构化日志系统](docs/STRUCTURED_LOGGING_GUIDE.md) | JSON 日志 + CLI 聚合工具 |
| [父进程监控机制](docs/PARENT_PROCESS_WATCHDOG.md) | 僵尸进程自动清理 |
| [ENU 坐标系统一](docs/old/ENU_DECOUPLED_V2_FINAL_SUMMARY.md) | 坐标系架构重构总结 |

### 历史文档

- 更多历史文档已归档到 [`docs/old/`](docs/old/) 目录
- AI 评审报告见 [`docs/评审报告/`](docs/评审报告/)

---

## 🔧 开发指南

### 创建自定义节点

```python
# my_node/main.py
from sdk.nodeflow_sdk import Node

class MyNode(Node):
    def setup(self):
        """初始化节点 (仅执行一次)"""
        self.counter = 0

    def loop(self):
        """主循环 (周期性执行)"""
        # 读取输入端口
        input_data = self.inputs["sensor_data"].read()

        # 处理数据
        self.counter += 1
        output_data = {"count": self.counter, "data": input_data}

        # 写入输出端口
        self.outputs["processed_data"].write(output_data)

    def cleanup(self):
        """清理资源 (节点退出时执行)"""
        print(f"Processed {self.counter} messages")

if __name__ == "__main__":
    node = MyNode()
    node.run()
```

**节点说明书** (`my_node/node.yaml`):
```yaml
name: "my_node"
version: "1.0.0"
description: "我的自定义节点"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "main.py"]

ports:
  inputs:
    - name: sensor_data
      type: sensor.raw
      description: 传感器数据输入

  outputs:
    - name: processed_data
      type: sensor.processed
      description: 处理后的数据输出
      buffer_size: 1048576  # 1MB (默认值，可省略)
      conflate: true        # Latest-value 模式 (默认值，可省略)

params:
  processing_mode:
    type: str
    default: "normal"
    description: "处理模式"
```

**部署节点**:
```bash
# 复制到节点库
cp -r my_node/ node-hub/

# 验证节点
python3 -m tools.cli.core.cli node info my_node

# 在 runtime.yaml 中使用
nodes:
  - id: processor
    package: my_node
    params:
      processing_mode: "advanced"
```

---

## 🛡️ 安全性

### 已修复的安全问题 (2025-12-22)

✅ **P0 Critical - 路径安全边界缺失**
- 问题: 4 个 MCP 工具存在任意文件读写漏洞
- 修复: 实现 `resolve_project_path()` 项目根目录约束机制
- 验证: 7/7 安全测试通过

✅ **P1 Major - 运行时启动超时**
- 问题: subprocess PIPE 阻塞导致启动失败
- 修复: 改用日志文件重定向，改进启动判定逻辑
- 效果: 启动时间从超时降至 3-5 秒

✅ **P2 Minor - 代码质量问题**
- 问题: 24 个 mypy 类型错误、依赖声明不一致
- 修复: 类型注解补全、依赖版本统一
- 结果: mypy 零错误、black 格式化 100% 合规

**详细报告**: [MCP_SERVICE_FIX_REPORT.md](docs/MCP_SERVICE_FIX_REPORT.md)

### 安全最佳实践

1. **路径验证**: 所有文件操作前验证路径在项目内
2. **输入校验**: 严格的参数类型和范围检查
3. **进程隔离**: 节点故障不影响框架核心
4. **最小权限**: Socket 文件权限控制
5. **审计日志**: 完整的操作和错误记录

---

## 📊 性能指标

### IPC 通信性能 (Hybrid Architecture)

| 指标 | 传统 Socket | Hybrid (SharedBuffer + ZMQ) | 提升 |
|------|------------|----------------------------|------|
| 数据持久性 | ❌ 未连接时丢失 | ✅ 持久化存储 | 🎯 100% |
| 连接延迟 | ~100ms (需重连) | <1ms (直接访问) | 🚀 100x |
| Late Joiner | ❌ 丢失历史数据 | ✅ 可读取历史 | 🎯 完整 |
| 内存占用 | 动态 | 固定 (1MB-50MB) | 📊 可控 |
| CPU 占用 | ~8% | ~3% | 📉 62% |

### 启动性能

- 节点发现: <100ms
- 拓扑分析: <50ms
- Buffer 预分配: <10ms
- 进程启动: <3s (10 节点)
- 总启动时间: <5s

---

## 🔄 最近更新

### 2026-01-02
- 🧹 **项目整理**: 归档历史文档、清理测试文件、更新目录结构
- 🔧 **端口类型修正**: 修复节点 YAML 端口类型，Web 编辑器连接正常
- 📚 **项目综述**: 新增 `docs/PROJECT_OVERVIEW_20260102.md` 完整项目介绍
- 📦 **测试模板**: 新增 `.test_template/` 便于快速创建节点测试

### 2026-01-01
- 📊 **结构��日志**: JSON 格式日志 + CLI 聚合工具 (`nodeflow logs`)
- ✅ **完整验证**: 端到端测试通过，642+ 条日志记录

### 2025-12-29
- 🛡️ **父进程监控**: ParentProcessWatchdog 防止孤儿进程

### 2025-12-27
- ✨ **ENU 坐标统一**: 坐标转换集中到 coord_transform 网关
- 🚨 **子进程清理**: 修复进程泄漏问题

### 2025-12-28
- 📜 **Schema 校验**: Pydantic 数据契约，CLI 健康检查

### 2025-12-26
- 🔒 **IPC 修复**: 共享内存竞态条件、序列号回绕处理
- 🧭 **坐标系对齐**: 修复控制器角速度符号

### 2025-12-24
- 📦 **缓冲区配置**: 灵活的输出端口缓冲区配置（1MB-50MB+）
- 🎯 **混合 IPC**: SharedBuffer + ZeroMQ 架构

### 2025-12-22
- 🔒 **安全加固**: 修复 MCP 服务路径穿越漏洞
- 🚀 **稳定性**: 运行时启动超时问题解决

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发流程

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

### 代码规范

- 使用 `black` 格式化代码 (`python3 -m black .`)
- 通过 `mypy` 类型检查 (`python3 -m mypy --ignore-missing-imports .`)
- 编写单元测试，保持覆盖率 >80%
- 遵循 [Conventional Commits](https://www.conventionalcommits.org/)

---

## 📄 许可证

本项目采用 [GPLv3 License](LICENSE) 开源协议。

---

## 🙏 致谢

- MCP (Model Context Protocol) by Anthropic
- msgpack-python by msgpack.org
- psutil by Giampaolo Rodola

---

## 📮 联系方式

- **问题反馈**: GitHub Issues
- **功能建议**: GitHub Discussions
- **文档贡献**: Pull Requests

---

*Built with ❤️ for robotics edge computing*