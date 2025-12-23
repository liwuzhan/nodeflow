# 机器人节点化框架（Robot NodeFlow）

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
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
- 🧪 **完善测试**: 单元测试、集成测试、Mock 节点覆盖

---

## 📋 系统要求

- **Python**: 3.10 或更高版本
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
# 基础示例 - 单节点运行
python3 -m runtime.main examples/test_mock_single.yaml

# 数据流示例 - 节点链
python3 -m runtime.main examples/test_mock_chain.yaml

# 查看可用节点
python3 -m tools.cli.core.cli node list
```

---

## 🏗️ 项目结构

```
robot-nodeflow/
├── runtime/              # 运行时框架核心
│   ├── config/           # 配置解析 (YAML Parser, Validator)
│   ├── node_hub/         # 节点发现与注册
│   ├── graph/            # 图拓扑分析 (循环检测、启动排序)
│   ├── orchestrator/     # 节点编排与生命周期管理
│   ├── ipc/              # IPC 通信 (Socket + MsgPack)
│   ├── monitoring/       # 监控与故障恢复
│   └── utils/            # 工具函数
│
├── sdk/                  # 节点开发 SDK
│   ├── nodeflow_sdk.py   # SDK 主类 (Node 基类)
│   └── port.py           # 端口抽象 (InputPort, OutputPort)
│
├── node-hub/             # 节点库 (可插拔节点包)
│   ├── global_coverage/  # GPS 覆盖率节点
│   ├── sim_gps/          # GPS 模拟器
│   ├── sim_imu/          # IMU 模拟器
│   ├── velocity_controller/  # 速度控制器
│   └── ...               # 更多节点
│
├── mcp_server.py         # MCP 服务 (AI 辅助调试)
├── runtime_manager.py    # 运行时进程管理
│
├── examples/             # 示例配置文件
│   ├── test_mock_single.yaml     # 单节点示例
│   ├── test_mock_chain.yaml      # 节点链示例
│   └── test_mock_pipeline.yaml   # 完整管道示例
│
├── tests/                # 测试套件
│   ├── unit/             # 单元测试
│   ├── integration/      # 集成测试
│   └── mcp/              # MCP 服务测试
│
├── docs/                 # 文档
│   ├── architecture.md              # 架构设计
│   ├── api-reference.md             # API 参考
│   ├── MCP_SERVICE_FIX_REPORT.md    # MCP 服务修复报告
│   └── SIMULATOR_GUIDE.md           # 仿真器使用指南
│
└── scripts/              # 开发工具脚本
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

---

## 📚 文档

| 文档 | 描述 |
|------|------|
| [Buffer 配置实现](docs/BUFFER_CONFIG_IMPLEMENTATION.md) | 缓冲区配置功能详细文档（2025-12-24）⭐ |
| [混合 IPC 架构](docs/ZMQ_HYBRID_IPC_IMPLEMENTATION.md) | SharedBuffer + ZeroMQ 混合方案（2025-12-24）⭐ |
| [Buffer 配置示例](examples/BUFFER_CONFIG_EXAMPLE.yaml) | 各类传感器缓冲区配置参考表 |
| [工作总结 2024-12-24](docs/SESSION_SUMMARY_20251224.md) | 最新工作总结报告 |
| [MCP 服务修复报告](docs/MCP_SERVICE_FIX_REPORT.md) | 安全修复、稳定性改进（2025-12-22） |
| [架构设计](docs/architecture.md) | 系统架构、设计决策、性能优化 |
| [API 参考](docs/api-reference.md) | SDK API、配置参考、节点开发指南 |

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

### 2025-12-24
- 📦 **缓冲区配置**: 实现灵活的输出端口缓冲区配置（1MB 默认、可配置 5-50MB+）
- 🎯 **混合 IPC 架构**: 完整实现 SharedBuffer + ZeroMQ 混合方案，解决分层启动数据丢失问题
- ✅ **完整测试**: 7/7 buffer 配置测试通过，100% 向后兼容
- 📚 **文档完善**: 新增实现文档、配置示例、工作总结（600+ 行）
- 🔧 **SDK 增强**: OutputPort 支持从环境变量读取 buffer 配置

### 2025-12-22
- 🔒 **安全加固**: 修复 MCP 服务路径穿越漏洞（P0 Critical）
- 🚀 **稳定性改进**: 解决运行时启动超时问题（subprocess PIPE）
- ✨ **代码质量**: mypy 类型错误清零、black 格式化完成
- 📝 **文档完善**: 新增详细修复报告（1,081 行）

### 2025-12-21
- 🔧 **消息序列化**: 从 JSON 迁移到 MsgPack（3x 性能提升）
- 🧪 **测试重组**: 统一测试框架、新增 Mock 节点库
- 📦 **Python 升级**: 迁移到 Python 3.12，类型注解完善

### 2025-12-20
- 🧠 **MCP 服务**: 实现 AI 辅助调试能力（7 个工具）
- 🎯 **拓扑优化**: 改进启动排序算法、循环依赖检测
- 📊 **监控增强**: 节点健康检查、自动重启机制

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

本项目采用 [MIT License](LICENSE) 开源协议。

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
