# 架构设计文档

## 系统概述

NodeFlow是一个配置驱动的节点编排框架，专为低速车辆边缘计算场景设计。

### 核心设计原则

1. **配置驱动**：通过YAML配置决定节点拓扑、参数和连接关系
2. **节点自治**：节点作为独立进程运行，崩溃不影响其他节点
3. **最小外部性**：默认数据通道只保留最新值（latest-value）
4. **实时性优先**：数据完整性、回放、持久化不由框架保证
5. **本机优先**：默认假设节点都在同一台机器上运行

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                   NodeFlow Runtime                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Config    │  │  Node Hub    │  │    Graph     │  │
│  │   Parser    │  │   Scanner    │  │   Analyzer   │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Socket    │  │   Node       │  │   Startup    │  │
│  │   Manager   │  │   Launcher   │  │  Coordinator │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌─────────────┐                                       │
│  │   Node      │                                       │
│  │   Monitor   │                                       │
│  └─────────────┘                                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
           │                    │                   │
           ▼                    ▼                   ▼
      ┌────────┐           ┌────────┐         ┌────────┐
      │ Node A │───────────│ Node B │─────────│ Node C │
      │  RTK   │    IPC    │Controller│   IPC  │ Logger │
      └────────┘           └────────┘         └────────┘
```

## 核心模块

### 1. 配置解析 (runtime/config/)

**职责**：解析和验证运行时配置和节点说明书

**关键类**：
- `YAMLParser`：解析runtime.yaml和node.yaml
- `ConfigValidator`：验证配置完整性和合法性
- `RuntimeConfig`、`NodeManifest`：配置数据模型

**数据流**：
```
runtime.yaml → YAMLParser → RuntimeConfig → Validator → ✓
```

### 2. 节点发现 (runtime/node_hub/)

**职责**：扫描node-hub目录，加载节点说明书

**关键类**：
- `NodeHubScanner`：扫描node-hub/目录
- `NodeRegistry`：缓存所有NodeManifest

**数据流**：
```
node-hub/ → Scanner → [packages] → Registry → {pkg: manifest}
```

### 3. 图分析 (runtime/graph/)

**职责**：分析节点依赖关系，计算启动顺序

**关键类**：
- `TopologyAnalyzer`：拓扑排序（Kahn算法）
- `GraphValidator`：图验证（端口、类型检查）

**算法**：Kahn算法拓扑排序
```
输入: nodes=[A,B,C], edges=[A→B, B→C]
步骤:
  1. 计算入度: A=0, B=1, C=1
  2. layer0: [A] (入度0)
  3. 移除A, 更新入度: B=0, C=1
  4. layer1: [B]
  5. 移除B, 更新入度: C=0
  6. layer2: [C]
输出: [[A], [B], [C]]
```

### 4. IPC通信 (runtime/ipc/)

**职责**：管理进程间通信（Unix Domain Socket）

**关键类**：
- `MessageProtocol`：消息编解码（4字节长度 + JSON）
- `SocketManager`：创建和管理socket文件
- `ServerChannel`、`ClientChannel`：通道抽象

**消息格式**：
```
[4字节小端序长度] + [JSON消息体]
例: [0x0F, 0x00, 0x00, 0x00] + {"data":"value"} (15字节)
```

### 5. 节点编排 (runtime/orchestrator/)

**职责**：按拓扑顺序启动节点进程

**关键类**：
- `EnvBuilder`：构建环境变量
- `NodeLauncher`：启动单个节点
- `StartupCoordinator`：协调多节点启动

**环境变量**：
```
NODE_ID=rtk_main
NODE_HUB_PATH=/node-hub
NODE_SOCKET_DIR=/tmp/nodeflow_sockets
NODE_IN_gps_cfg=/tmp/nodeflow_rtk_main.gps_cfg.in
NODE_OUT_gps_fix=/tmp/nodeflow_rtk_main.gps_fix.out
```

**启动策略**：
```
layers = [[A], [B,C], [D]]

执行:
  1. 启动layer0: A (单独)
  2. 等待A启动完成
  3. 启动layer1: B和C (并行)
  4. 等待B、C启动完成
  5. 启动layer2: D (单独)
```

### 6. 节点监控 (runtime/monitoring/)

**职责**：监控节点健康，处理崩溃和重启

**关键类**：
- `NodeMonitor`：监控所有节点进程
- `RetryTracker`：跟踪重试次数

**重启策略**：
```
崩溃检测 → 记录失败 → 检查重试次数 → 指数退避 → 重启
              ↓                              ↓
         retry_count++                  backoff * 2^n
              ↓                              ↓
      < max_retries?                    sleep(backoff)
              ↓                              ↓
         YES / NO                          restart()
```

### 7. 节点SDK (sdk/)

**职责**：为节点开发者提供便捷API

**关键类**：
- `NodeFlowSDK`：主入口
- `InputPort`、`OutputPort`：端口抽象
- `LatestValueReader`：最新值语义实现

**最新值语义**：
```python
def read_latest(sock):
    latest = None
    while True:
        try:
            msg = decode(sock)  # 非阻塞
            if msg:
                latest = msg  # 覆盖旧值
        except BlockingIOError:
            break  # 无更多数据
    return latest  # 只返回最新的
```

## 数据流

### 完整启动流程

```
1. main.py启动
   ↓
2. 解析runtime.yaml
   ↓
3. 验证配置
   ↓
4. 扫描node-hub/，加载所有node.yaml
   ↓
5. 验证图（节点、端口、类型）
   ↓
6. 拓扑排序 → [[layer0], [layer1], ...]
   ↓
7. 初始化Socket管理器
   ↓
8. 按层次启动节点
   │  ├─ 构建环境变量
   │  ├─ 构建命令（追加--params）
   │  ├─ subprocess.Popen()
   │  └─ 等待启动完成
   ↓
9. 启动监控线程
   ↓
10. 主循环（等待Ctrl+C）
   ↓
11. 清理（关闭节点、清理socket）
```

### 节点间通信流程

```
发送端 (OutputPort)                接收端 (InputPort)
     │                                    │
     ├─ 创建Socket服务端                  │
     │  bind(socket_path)                 │
     │  listen()                          │
     │                                    ├─ 连接到服务端
     │                                    │  connect(socket_path)
     ├─ accept() ───────────────────────→ │
     │                                    │
     ├─ send(data)                        │
     │  encode(data)                      │
     │  sendall(msg) ────────────────────→ │
     │                                    ├─ recv_latest()
     │                                    │  while True:
     │                                    │    msg = decode()
     │                                    │    latest = msg
     │                                    │  return latest
```

## 目录结构

```
节点化/
├── runtime/           # 运行时框架
│   ├── config/        # 配置解析
│   ├── node_hub/      # 节点发现
│   ├── graph/         # 图分析
│   ├── orchestrator/  # 节点编排
│   ├── ipc/           # IPC通信
│   ├── monitoring/    # 监控恢复
│   ├── utils/         # 工具函数
│   └── main.py        # 主入口
├── sdk/               # 节点SDK
│   ├── nodeflow_sdk.py
│   ├── port.py
│   └── latest_value_reader.py
├── node-hub/          # 节点库
│   ├── rtk/
│   └── controller/
├── examples/          # 示例配置
│   └── runtime.yaml
├── tests/             # 测试套件
└── docs/              # 文档
```

## 扩展性

### 未来扩展方向

1. **Web控制台**：实时查看节点状态、日志、性能指标
2. **远程节点**：支持跨机器节点（网络Socket）
3. **录包回放**：记录数据流并支持离线回放
4. **性能监控**：CPU、内存、通信带宽统计
5. **配置热更新**：部分参数无需重启即可生效

### 架构预留

- **抽象接口**：IPC模块提供抽象接口，便于替换为网络Socket
- **插件机制**：监控模块支持自定义监控器
- **配置扩展**：runtime.yaml预留`extensions`字段

## 性能考虑

### IPC性能

- Unix Domain Socket比TCP Socket快30-50%
- JSON序列化简单但有开销，未来可替换为MessagePack或Protobuf
- 最新值语义避免队列积压，保证实时性

### 启动性能

- 同层节点并行启动，减少总启动时间
- 拓扑排序O(V+E)复杂度，适用于大规模图

### 内存占用

- 每个节点独立进程，隔离性好但内存开销较大
- Socket缓冲区自动管理，避免内存泄漏

## 安全性

### 进程隔离

- 节点崩溃不影响框架和其他节点
- 节点异常不会传播到框架层

### 资源限制

- Socket文件权限控制
- 进程生命周期由框架管理
- 支持优雅关闭和强制kill

## 总结

NodeFlow通过配置驱动、节点自治、最新值语义等设计原则，实现了：

1. ✅ 灵活的节点组合（更换机具=换配置）
2. ✅ 可靠的进程管理（崩溃自动重启）
3. ✅ 高效的数据流（latest-value，实时性）
4. ✅ 简洁的开发体验（SDK封装复杂度）
5. ✅ 完整的监控机制（健康检查、故障恢复）

适用于需要频繁调整策略、快速部署的边缘计算场景。
