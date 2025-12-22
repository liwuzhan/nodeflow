# API参考文档

## 节点SDK API

### NodeFlowSDK 主类

```python
from sdk.nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK(log_level="INFO") as sdk:
    # 获取节点信息
    node_id = sdk.node_id              # 节点实例ID
    node_hub_path = sdk.node_hub_path  # 节点库路径
    socket_dir = sdk.socket_dir        # Socket临时目录

    # 参数访问
    params = sdk.params                # 所有参数字典
    value = sdk.get_param('key', default_value)  # 获取参数（可选）
    value = sdk.require_param('key')   # 获取必填参数

    # 端口管理
    input_port = sdk.create_input_port('port_name')
    output_port = sdk.create_output_port('port_name')

    # 日志
    sdk.logger.info("消息")
    sdk.logger.warning("警告")
    sdk.logger.error("错误")
```

### InputPort 输入端口

```python
input_port = sdk.create_input_port('gps_fix')

# 非阻塞接收最新值
latest_data = input_port.recv_latest()
if latest_data:
    latitude = latest_data['latitude']
    longitude = latest_data['longitude']

# 阻塞接收最新值（等待直到有数据）
data = input_port.recv_latest_blocking(timeout=5.0)

# 关闭端口
input_port.close()
```

### OutputPort 输出端口

```python
output_port = sdk.create_output_port('control_cmd')

# 发送数据（字典）
output_port.send({
    'speed': 2.5,
    'steering': 0.15,
    'timestamp': time.time()
})

# 关闭端口
output_port.close()
```

## 运行时框架API

### 配置加载

```python
from runtime.config.yaml_parser import YAMLParser
from runtime.config.validator import ConfigValidator

parser = YAMLParser()

# 解析运行配置
config = parser.parse_runtime_config('examples/runtime.yaml')
print(config.graph_id)
print(config.nodes)
print(config.edges)

# 解析节点说明书
manifest = parser.parse_node_manifest('node-hub/rtk/node.yaml')
print(manifest.name)
print(manifest.inputs)
print(manifest.outputs)

# 验证配置
validator = ConfigValidator()
result = validator.validate_runtime_config(config)
if not result.is_valid:
    print(result.errors)
```

### 节点发现

```python
from runtime.node_hub.node_registry import NodeRegistry

registry = NodeRegistry('./node-hub')
registry.load_all()

# 获取所有节点包
packages = registry.get_all_packages()  # ['rtk', 'controller']

# 获取节点说明书
manifest = registry.get_manifest('rtk')

# 检查节点包是否存在
exists = registry.has_package('rtk')

# 获取启动入口
entrypoint = registry.get_entrypoint('rtk', platform='linux')
```

### 拓扑分析

```python
from runtime.graph.topology import TopologyAnalyzer

analyzer = TopologyAnalyzer(nodes, edges)

# 拓扑排序，返回分层启动顺序
layers = analyzer.topological_sort()
# [[node_a], [node_b, node_c], [node_d]]

# 获取节点依赖
deps = analyzer.get_dependencies('node_b')  # [node_a]

# 获取依赖该节点的节点
dependents = analyzer.get_dependents('node_a')  # [node_b]

# 判断节点是否无依赖
independent = analyzer.is_independent('node_a')  # True
```

### Socket管理

```python
from runtime.ipc.socket_manager import SocketManager

socket_manager = SocketManager('/tmp/nodeflow_sockets')
socket_manager.initialize()

# 创建通道路径
path = socket_manager.create_channel_path(
    node_id='rtk_main',
    port_name='gps_fix',
    direction='out'
)
# /tmp/nodeflow_sockets/nodeflow_rtk_main.gps_fix.out

# 获取所有socket路径
paths = socket_manager.get_all_socket_paths()

# 清理socket文件
socket_manager.cleanup()
```

### 消息协议

```python
from runtime.ipc.protocol import MessageProtocol
import socket

# 编码消息
data = {'latitude': 39.9042, 'longitude': 116.4074}
encoded = MessageProtocol.encode(data)
# [4字节长度] + [JSON数据]

# 解码消息
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
msg = MessageProtocol.decode(sock)
# {'latitude': 39.9042, 'longitude': 116.4074}
```

### 节点启动

```python
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.orchestrator.startup_coordinator import StartupCoordinator

launcher = NodeLauncher(node_hub_path, socket_manager)

# 启动单个节点
process = launcher.launch(node_instance, manifest)
print(f"PID: {process.pid}")

# 检查进程健康
is_alive = launcher.check_process_health(process, 'node_id')

# 优雅关闭
launcher.terminate_process(process, 'node_id', timeout=5.0)

# 协调多节点启动
coordinator = StartupCoordinator(launcher, registry)
processes = coordinator.startup_nodes(layers, nodes_dict)

# 关闭所有节点
coordinator.shutdown_nodes(processes, shutdown_timeout=5.0)
```

### 节点监控

```python
from runtime.monitoring.node_monitor import NodeMonitor

monitor = NodeMonitor(restart_policy)

def restart_callback(node_id):
    return launcher.launch(node, manifest)

monitor.start_monitoring(processes, restart_callback)

# 获取节点状态
status = monitor.get_node_status('rtk_main')
# {
#   'running': True,
#   'pid': 12345,
#   'exit_code': None,
#   'retry_status': {...}
# }

# 获取所有节点状态
all_status = monitor.get_all_status()

# 获取运行中的节点
running = monitor.get_running_nodes()  # ['rtk_main', 'controller_main']

# 停止监控
monitor.stop()
```

## 配置文件格式

### runtime.yaml 运行配置

```yaml
graph_id: my_graph                  # 图ID
graph_version: 1                    # 图版本
node_hub_path: ./node-hub          # 节点库路径

nodes:                              # 节点实例列表
  - id: rtk_main                    # 实例ID（唯一）
    package: rtk                    # 节点包名
    params:                         # 透传参数
      device: "/dev/ttyUSB0"
      baudrate: 115200

edges:                              # 连接关系列表
  - from: rtk_main.gps_fix          # 源节点.输出端口
    to: controller_main.gps_fix     # 目标节点.输入端口
    type: gps.fix                   # 端口类型（可选）

restart_policy:                     # 重启策略（可选）
  max_retries: 3                    # 最大重试次数
  backoff_ms: 500                   # 重试退避时间（毫秒）
```

### node.yaml 节点说明书

```yaml
name: rtk                           # 节点名
version: 0.1.0                      # 版本
description: RTK GPS定位节点        # 描述

entrypoints:                        # 启动入口（按平台）
  linux:
    kind: python                    # 入口类型
    cmd: ["python3", "run.py"]      # 启动命令

ports:                              # 端口定义
  inputs:                           # 输入端口
    - name: config                  # 端口名
      type: config.rtk              # 端口类型
      description: RTK配置输入

  outputs:                          # 输出端口
    - name: gps_fix
      type: gps.fix
      description: GPS定位输出

params:                             # 参数schema（可选）
  device:
    type: string                    # 参数类型
    required: true                  # 是否必填
    description: 串口设备路径

  baudrate:
    type: int
    default: 115200                 # 默认值
    description: 波特率
```

## 环境变量

框架自动注入以下环境变量：

```bash
# 通用变量
NODE_ID=rtk_main                    # 节点实例ID
NODE_HUB_PATH=/path/to/node-hub    # 节点库路径
NODE_SOCKET_DIR=/tmp/nodeflow_sockets  # Socket临时目录

# 端口特定变量
NODE_IN_config=/tmp/.../socket      # 输入端口socket路径
NODE_OUT_gps_fix=/tmp/.../socket    # 输出端口socket路径
```

节点可通过以下方式访问：

```python
import os

node_id = os.getenv('NODE_ID')
socket_path = os.getenv('NODE_IN_config')
```

## 错误处理

```python
from runtime.utils.errors import *

try:
    config = parser.parse_runtime_config(path)
except YAMLParseError as e:
    print(f"配置解析失败: {e}")

try:
    registry.get_manifest(package)
except NodeNotFoundError as e:
    print(f"节点包不存在: {e}")

try:
    topology.topological_sort()
except CyclicDependencyError as e:
    print(f"检测到循环依赖: {e.nodes}")
```

## 日志API

```python
from runtime.utils.logger import setup_logger, get_logger

# 设置全局日志
logger = setup_logger("nodeflow", log_level="DEBUG")

# 在模块中获取日志器
logger = get_logger(__name__)

logger.debug("详细信息")
logger.info("重要信息")
logger.warning("警告信息")
logger.error("错误信息")
```

## 示例代码

### 最小化节点

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK() as sdk:
    output = sdk.create_output_port('output')

    for i in range(100):
        output.send({'count': i})
```

### 完整节点示例

```python
#!/usr/bin/env python3
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Started")

        # 参数
        rate = sdk.get_param('rate', 10.0)

        # 端口
        input_port = sdk.create_input_port('input')
        output_port = sdk.create_output_port('output')

        # 主循环
        try:
            for i in range(1000):
                data = input_port.recv_latest()

                if data:
                    processed = process(data)
                    output_port.send(processed)

                time.sleep(1.0 / rate)

        except KeyboardInterrupt:
            sdk.logger.info("Shutting down")

if __name__ == '__main__':
    main()
```

## 更多信息

- 详见 [快速开始](快速开始.md)
- 详见 [架构设计](architecture.md)
- 详见 [PRD文档](robot-nodeflow-prd-v0.1.md)
