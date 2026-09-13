# NodeFlow 节点依赖管理指南

## 概述

每个节点都有独立的 `requirements.txt` 文件，管理该节点的特定依赖。使用一键安装脚本可以批量安装所有节点的依赖。

## 依赖结构

```
node/
├── requirements.txt                 # 核心 SDK 依赖（pydantic, pytest, pyzmq 等）
├── tools/
│   └── install_node_deps.py        # 一键安装脚本
└── node-hub/
    ├── global_coverage/
    │   └── requirements.txt        # shapely, numpy
    ├── network_input/
    │   └── requirements.txt        # pillow, numpy, requests
    ├── yolo_detector/
    │   └── requirements.txt        # opencv-python, numpy, ultralytics
    ├── logger/
    │   └── requirements.txt        # fastapi, uvicorn, websockets
    ├── trajectory_viz/
    │   └── requirements.txt        # flask, socketio, numpy
    ├── sim_input/
    │   └── requirements.txt        # pyzmq
    └── sim_output/
        └── requirements.txt        # pyzmq
```

## 快速开始

### 1. 安装核心依赖
```bash
pip3 install -r requirements.txt
```

### 2. 安装所有节点依赖
```bash
# 先预览要安装的内容
python3 tools/install_node_deps.py --dry-run

# 执行实际安装
python3 tools/install_node_deps.py
```

### 3. 选择性安装

如果只需要特定节点：
```bash
# 仅安装全局规划和网络输入节点
python3 tools/install_node_deps.py --nodes global_coverage network_input
```

如果要跳过某些节点（如 YOLO 需要大量依赖）：
```bash
# 跳过 YOLO 检测节点
python3 tools/install_node_deps.py --skip yolo_detector
```

## 常见场景

### 场景 1: 新设备部署

```bash
cd /path/to/node
pip3 install -r requirements.txt
python3 tools/install_node_deps.py
```

### 场景 2: 添加新节点

1. 在 `node-hub/your_node/` 创建 `requirements.txt`
2. 列出该节点的特定依赖
3. 运行安装脚本自动检测并安装

```bash
# 自动检测到新节点并安装
python3 tools/install_node_deps.py --nodes your_node
```

### 场景 3: 仅开发特定节点

如果你只需要开发某个节点，无需安装所有依赖：

```bash
# 仅安装核心 SDK + 特定节点
pip3 install -r requirements.txt
python3 tools/install_node_deps.py --nodes global_coverage
```

## 依赖说明

### 核心依赖（根目录 requirements.txt）
- **pydantic**: 数据验证和序列化（几乎所有节点都需要）
- **pytest**: 测试框架
- **pyzmq**: 消息队列通信
- **msgpack**: 数据序列化
- **psutil**: 进程管理

### 节点特定依赖

| 节点 | 依赖 | 说明 |
|------|------|------|
| global_coverage | shapely, numpy | 几何运算和路径规划 |
| network_input | pillow, requests | 网络图像接收 |
| yolo_detector | opencv-python, ultralytics | 目标检测（依赖较重） |
| logger | fastapi, uvicorn | Web 日志服务 |
| trajectory_viz | flask, socketio | 可视化 Web 界面 |
| sim_input/output | pyzmq | 仿真消息通信 |

### 注意事项

1. **pydantic 已在核心依赖中**：大部分节点只依赖 pydantic，无需单独的 requirements.txt
2. **可选依赖**：如果不使用某个节点（如 YOLO），可以跳过安装以节省空间和时间
3. **版本约束**：所有依赖都有最低版本要求，确保兼容性

## 故障排除

### 问题 1: ModuleNotFoundError

```bash
# 检查缺少哪些依赖
python3 tools/install_node_deps.py --dry-run

# 安装缺失的依赖
python3 tools/install_node_deps.py --nodes <节点名>
```

### 问题 2: 网络问题导致安装失败

```bash
# 使用国内镜像源
pip3 install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
python3 tools/install_node_deps.py
```

### 问题 3: 权限问题

```bash
# 使用 --user 参数安装到用户目录
pip3 install --user -r requirements.txt
```

## 最佳实践

1. **新设备部署**：先安装核心依赖，再根据需要安装节点依赖
2. **开发时**：使用虚拟环境隔离不同项目的依赖
3. **CI/CD**：在自动化测试中使用 `--dry-run` 验证依赖完整性
4. **添加新依赖**：
   - 优先使用核心依赖中的包
   - 新增特殊依赖时，在节点目录创建 requirements.txt
   - 指定最低版本约束（如 `>=2.0.0`）

## 脚本帮助

查看完整帮助信息：
```bash
python3 tools/install_node_deps.py --help
```
