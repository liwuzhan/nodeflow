# NodeFlow SDK API 参考

完整的 SDK API 文档，包含所有类、方法和参数。

## 目录

- [NodeFlowSDK](#nodeflowsdk)
- [InputPort](#inputport)
- [OutputPort](#outputport)
- [StructuredLogger](#structuredlogger)
- [环境变量](#环境变量)

---

## NodeFlowSDK

主类，提供节点开发的核心 API。

### 初始化

```python
from nodeflow_sdk import NodeFlowSDK

sdk = NodeFlowSDK(
    log_level: str = "INFO",
    enable_parent_watchdog: bool = True
)
```

**参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `log_level` | str | "INFO" | 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| `enable_parent_watchdog` | bool | True | 是否启用父进程监控（自动检测孤儿进程） |

**异常**

- `ValueError` - NODE_ID 环境变量未设置

### 上下文管理器（推荐）

```python
# 自动清理资源
with NodeFlowSDK(log_level="INFO") as sdk:
    # 使用 SDK
    input_port = sdk.create_input_port("data")
    output_port = sdk.create_output_port("result")
# 自动调用 sdk.shutdown()
```

### 属性

```python
sdk.node_id: str              # 节点实例ID
sdk.logger: StructuredLogger  # 结构化日志器
sdk.params: Dict[str, Any]    # 节点参数
sdk.inputs: Dict[str, InputPort]   # 输入端口映射
sdk.outputs: Dict[str, OutputPort] # 输出端口映射
```

### 方法

#### get_param()

```python
value = sdk.get_param(
    key: str,
    default: Any = None
) -> Any
```

获取参数值（如果缺失返回默认值）。

**参数**

| 参数 | 说明 |
|------|------|
| `key` | 参数名 |
| `default` | 默认值（可选） |

**返回**

参数值或默认值

**示例**

```python
timeout = sdk.get_param('timeout', 1000)
frequency = sdk.get_param('frequency', 50.0)
```

#### require_param()

```python
value = sdk.require_param(key: str) -> Any
```

获取必填参数（缺失时抛出异常）。

**参数**

| 参数 | 说明 |
|------|------|
| `key` | 参数名 |

**异常**

- `ValueError` - 参数不存在

**示例**

```python
api_key = sdk.require_param('api_key')
```

#### create_input_port()

```python
port = sdk.create_input_port(
    port_name: str
) -> InputPort
```

创建输入端口（读取数据）。

**参数**

| 参数 | 说明 |
|------|------|
| `port_name` | 端口名（必须与 node.yaml 一致） |

**异常**

- `ValueError` - 端口未配置

**返回**

InputPort 对象

**示例**

```python
rtk_port = sdk.create_input_port('rtk_fix')
pose_port = sdk.create_input_port('pose_enu')
```

#### create_output_port()

```python
port = sdk.create_output_port(
    port_name: str,
    schema: Optional[Type[BaseModel]] = None
) -> OutputPort
```

创建输出端口（发送数据）。

**参数**

| 参数 | 说明 |
|------|------|
| `port_name` | 端口名（必须与 node.yaml 一致） |
| `schema` | Pydantic 数据模型（可选，用于验证） |

**异常**

- `ValueError` - 端口未配置

**返回**

OutputPort 对象

**示例**

```python
# 不带 Schema
output = sdk.create_output_port('result')

# 带 Schema 验证
from pydantic import BaseModel

class Position(BaseModel):
    x: float
    y: float
    z: float

output = sdk.create_output_port('position', schema=Position)
```

#### get_input_port()

```python
port = sdk.get_input_port(port_name: str) -> Optional[InputPort]
```

获取已创建的输入端口。

**参数**

| 参数 | 说明 |
|------|------|
| `port_name` | 端口名 |

**返回**

InputPort 对象或 None

#### get_output_port()

```python
port = sdk.get_output_port(port_name: str) -> Optional[OutputPort]
```

获取已创建的输出端口。

**参数**

| 参数 | 说明 |
|------|------|
| `port_name` | 端口名 |

**返回**

OutputPort 对象或 None

#### is_input_port_connected()

```python
is_connected = sdk.is_input_port_connected(port_name: str) -> bool
```

检查输入端口是否已连接。

**参数**

| 参数 | 说明 |
|------|------|
| `port_name` | 端口名 |

**返回**

True 表示已连接

#### get_input_port_status()

```python
status = sdk.get_input_port_status(port_name: str) -> Optional[str]
```

获取输入端口的连接状态。

**参数**

| 参数 | 说明 |
|------|------|
| `port_name` | 端口名 |

**返回**

- "connecting" - 初始化中
- "connected" - 已连接
- "disconnected" - 已断开
- None - 端口不存在

#### shutdown()

```python
sdk.shutdown() -> None
```

手动关闭 SDK，释放所有资源。

**示例**

```python
sdk = NodeFlowSDK()
try:
    # 使用 SDK
    pass
finally:
    sdk.shutdown()
```

---

## InputPort

输入端口，用于读取来自其他节点的数据。

### 初始化

```python
# 通过 SDK 创建（推荐）
port = sdk.create_input_port('port_name')

# 直接创建（高级用途）
from sdk.port import InputPort
port = InputPort('port_name', 'ipc:///tmp/nodeflow/source_node.source_port')
```

### 属性

```python
port.name: str                # 端口名
port.zmq_address: str         # ZMQ 地址
port.source_node: Optional[str]  # 源节点 ID
port.source_port: Optional[str]  # 源端口名
port.last_sequence: int       # 最后读取的序列号
```

### 方法

#### recv_latest()

```python
data = port.recv_latest() -> Optional[Dict[str, Any]]
```

**非阻塞**读取最新数据（推荐）。

- 如果有新数据，返回最新值
- 如果无新数据，返回 None
- 首次连接时会读取历史数据（解决 Late-Joiner 问题）

**返回**

数据字典或 None

**示例**

```python
while True:
    data = input_port.recv_latest()
    if data:
        print(f"收到: {data}")
    else:
        print("等待数据...")
    time.sleep(0.01)
```

#### read()

```python
data = port.read() -> Optional[Dict[str, Any]]
```

读取当前缓冲区中的数据（同 `recv_latest()`）。

#### read_blocking()

```python
data = port.read_blocking(
    timeout: Optional[float] = None
) -> Optional[Dict[str, Any]]
```

**阻塞**读取数据，等待新消息。

**参数**

| 参数 | 说明 |
|------|------|
| `timeout` | 超时时间（秒），None 表示无限等待 |

**返回**

数据字典或 None（超时）

**示例**

```python
# 等待 1 秒获取新数据
data = port.read_blocking(timeout=1.0)
if data:
    print(f"收到新数据: {data}")
```

#### is_connected()

```python
is_connected = port.is_connected() -> bool
```

检查端口是否已连接。

**返回**

True 表示已连接

#### get_connection_state()

```python
state = port.get_connection_state() -> Optional[str]
```

获取详细的连接状态。

**返回**

- "connecting" - 初始化中
- "connected" - 已连接
- "disconnected" - 已断开

#### close()

```python
port.close() -> None
```

关闭端口，释放资源。

---

## OutputPort

输出端口，用于发送数据到其他节点。

### 初始化

```python
# 通过 SDK 创建（推荐）
port = sdk.create_output_port('port_name')

# 带 Schema 验证
from pydantic import BaseModel

class Data(BaseModel):
    value: float

port = sdk.create_output_port('port_name', schema=Data)

# 直接创建（高级用途）
from sdk.port import OutputPort
port = OutputPort('port_name', 'ipc:///tmp/nodeflow/node_id.port_name')
```

### 属性

```python
port.name: str              # 端口名
port.zmq_address: str       # ZMQ 地址
port.buffer_name: str       # 共享缓冲区名称
port.buffer_size: int       # 缓冲区大小（字节）
port.schema: Optional[Type[BaseModel]]  # Schema 模型
port.conflate: bool         # 是否启用覆盖模式
```

### 方法

#### send()

```python
port.send(
    data: Union[Dict[str, Any], BaseModel]
) -> None
```

发送数据到输出端口。

**步骤**

1. 如果配置了 Schema，进行数据验证
2. 将数据写入共享缓冲区（持久化）
3. 发送 ZMQ 通知（实时通知）

**参数**

| 参数 | 说明 |
|------|------|
| `data` | 数据字典或 Pydantic 模型实例 |

**异常**

- `ValueError` - Schema 验证失败（strict 模式）
- `Exception` - 其他发送错误

**示例**

```python
# 发送字典
port.send({
    'x': 100.5,
    'y': 200.3,
    'z': 50.0
})

# 发送 Pydantic 对象
from pydantic import BaseModel

class Position(BaseModel):
    x: float
    y: float
    z: float

position = Position(x=100.5, y=200.3, z=50.0)
port.send(position)
```

#### get_schema_json()

```python
schema_json = port.get_schema_json() -> Optional[Dict[str, Any]]
```

获取端口 Schema 的 JSON 描述。

**返回**

JSON Schema 字典或 None

**示例**

```python
schema = output_port.get_schema_json()
if schema:
    print(f"Schema 描述:\n{json.dumps(schema, indent=2)}")
```

#### close()

```python
port.close() -> None
```

关闭端口，释放资源。

---

## StructuredLogger

结构化日志器，提供 JSON 格式日志 + 控制台输出。

### 初始化

```python
from sdk.structured_logger import StructuredLogger

logger = StructuredLogger(
    node_id: str,
    log_level: str = "INFO",
    log_dir: str = "/tmp/nodeflow_logs",
    enable_json: bool = True,
    enable_console: bool = True
)
```

**参数**

| 参数 | 说明 |
|------|------|
| `node_id` | 节点 ID |
| `log_level` | 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| `log_dir` | 日志目录 |
| `enable_json` | 是否启用 JSON 文件输出 |
| `enable_console` | 是否启用控制台输出 |

### 通过 SDK 使用

```python
# SDK 自动创建和配置
with NodeFlowSDK(log_level="INFO") as sdk:
    sdk.logger.info("消息")
```

### 方法

#### debug()

```python
sdk.logger.debug(
    msg: str,
    **kwargs
) -> None
```

记录 DEBUG 级别日志。

**参数**

| 参数 | 说明 |
|------|------|
| `msg` | 日志消息 |
| `**kwargs` | 自定义字段（任意关键字参数） |

**示例**

```python
sdk.logger.debug("处理数据点",
    index=0,
    value=3.14,
    processing_time_ms=10.5)
```

#### info()

```python
sdk.logger.info(
    msg: str,
    **kwargs
) -> None
```

记录 INFO 级别日志。

**示例**

```python
sdk.logger.info("节点启动完成",
    version="1.0",
    node_count=5)
```

#### warning()

```python
sdk.logger.warning(
    msg: str,
    **kwargs
) -> None
```

记录 WARNING 级别日志。

**示例**

```python
sdk.logger.warning("连接延迟过高",
    latency_ms=2000,
    threshold_ms=1000)
```

#### error()

```python
sdk.logger.error(
    msg: str,
    exc_info: Any = None,
    **kwargs
) -> None
```

记录 ERROR 级别日志。

**参数**

| 参数 | 说明 |
|------|------|
| `msg` | 日志消息 |
| `exc_info` | 异常信息（True 表示捕获当前异常） |
| `**kwargs` | 自定义字段 |

**示例**

```python
try:
    result = process(data)
except Exception as e:
    sdk.logger.error("处理失败",
        exc_info=True,
        data_size=len(data))
```

#### critical()

```python
sdk.logger.critical(
    msg: str,
    exc_info: Any = None,
    **kwargs
) -> None
```

记录 CRITICAL 级别日志。

**示例**

```python
if not simulator.is_connected():
    sdk.logger.critical("仿真器离线",
        host="localhost",
        port=5555)
```

#### close()

```python
sdk.logger.close() -> None
```

关闭日志器，释放文件处理器。

---

## 环境变量

SDK 通过以下环境变量进行配置（由框架自动设置）：

### 基础配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `NODE_ID` | 节点实例 ID | `sim_output` |
| `NODE_HUB_PATH` | 节点库根目录 | `./node-hub` |
| `NODE_SOCKET_DIR` | Socket 临时目录 | `/tmp/nodeflow` |

### 端口配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `NODE_IN_<PORT>` | 输入端口 ZMQ 地址 | `ipc:///tmp/nodeflow/source.port` |
| `NODE_OUT_<PORT>` | 输出端口 ZMQ 地址 | `ipc:///tmp/nodeflow/node_id.port` |
| `NODE_OUT_<PORT>_BUFFER_SIZE` | 输出缓冲区大小 | `10485760` (10MB) |
| `NODE_OUT_<PORT>_CONFLATE` | 是否启用覆盖模式 | `true` |

### 监控配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `NODE_PARENT_WATCHDOG` | 启用父进程监控 | `true` |
| `NODE_WATCHDOG_INTERVAL` | 监控检查间隔（秒） | `1.0` |

### 日志配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `NODEFLOW_LOG_DIR` | 日志目录 | `/tmp/nodeflow_logs` |
| `NODE_SCHEMA_VALIDATION` | Schema 验证模式 | `off/loose/strict` |

### Schema 验证模式

| 模式 | 行为 |
|------|------|
| `off` | 禁用验证（默认，最快） |
| `loose` | 验证失败时警告但继续 |
| `strict` | 验证失败时抛出异常 |

## 常见问题

### Q: 如何在节点启动时立即读取一次数据？

A: 第一次调用 `recv_latest()` 会读取历史数据（如果有的话）。

```python
# 确保首先创建输入端口
port = sdk.create_input_port('data')
time.sleep(0.1)  # 等待连接建立

# 首次读取会获取历史数据
initial_data = port.recv_latest()
```

### Q: 如何在多个节点间同步数据？

A: 使用相同的缓冲区大小和覆盖模式（conflate）。

```yaml
ports:
  outputs:
    - name: shared_data
      buffer_size: 10485760
      conflate: true
```

### Q: 性能瓶颈在哪里？

A: 日志输出是最常见的瓶颈。在生产环境中降低日志级别：

```python
# 生产环境
sdk = NodeFlowSDK(log_level="WARNING")

# 或通过环境变量
export NODE_SCHEMA_VALIDATION=off
```

### Q: 如何处理缓冲区溢出？

A: 增加缓冲区大小或增加消费频率。

```yaml
ports:
  outputs:
    - name: output
      buffer_size: 52428800  # 50MB
```

---

**参考资源**

- [快速入门](SDK_GETTING_STARTED.md)
- [最佳实践](SDK_BEST_PRACTICES.md)
- [日志系统](STRUCTURED_LOGGING_GUIDE.md)
- [示例节点](../node-hub/sim_output/run.py)
