# 机器人节点化框架（Robot NodeFlow）

配置驱动的节点编排框架，专为低速车辆边缘计算场景设计。

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

或者安装为可编辑包：

```bash
pip install -e .
```

### 运行示例

```bash
# 运行框架
python -m runtime.main examples/runtime.yaml
```

## 项目结构

```
├── runtime/          # 运行时框架核心
│   ├── config/       # 配置解析
│   ├── node_hub/     # 节点发现与加载
│   ├── graph/        # 图拓扑分析
│   ├── orchestrator/ # 节点编排与启动
│   ├── ipc/          # IPC通信管理
│   ├── monitoring/   # 监控与故障恢复
│   └── utils/        # 工具函数
├── sdk/              # 节点开发SDK
├── node-hub/         # 节点库
├── examples/         # 示例配置
├── tests/            # 测试套件
└── scripts/          # 开发工具脚本
```

## 核心概念

### 节点（Node）
独立运行的进程，通过端口（Ports）进行数据交换。

### 运行配置（Runtime YAML）
定义节点实例、连接关系和启动参数的配置文件。

### 节点说明书（Node Manifest）
每个节点包必须包含的 `node.yaml` 文件，描述节点的端口、参数和启动入口。

### IPC通信
基于Unix Domain Socket + JSON序列化 + latest-value语义的进程间通信。

## 开发指南

参见 `docs/` 目录：
- [架构设计](docs/architecture.md)
- [API参考](docs/api-reference.md)
- [PRD文档](docs/robot-nodeflow-prd-v0.1.md)

## 许可

MIT License
