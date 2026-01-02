# NodeFlow SDK 快速入门

欢迎使用 NodeFlow SDK！这是一个为构建分布式传感器-控制系统设计的高性能节点开发工具包。

## 概述

NodeFlow SDK 提供了一套完整的 API，让你可以快速开发节点：

- **参数管理** - 从 YAML 配置接收参数
- **端口通信** - 高效的进程间通信（共享内存 + ZeroMQ）
- **结构化日志** - JSON 格式日志 + 实时控制台输出
- **Schema 验证** - 可选的 Pydantic 数据验证
- **生命周期管理** - 父进程监控、资源清理

## 最小节点示例

```python
#!/usr/bin/env python3
"""最小的 NodeFlow 节点"""

from nodeflow_sdk import NodeFlowSDK

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"节点 {sdk.node_id} 启动")

        # 创建输入端口（读取数据）
        input_port = sdk.create_input_port("input_data")

        # 创建输出端口（发送数据）
        output_port = sdk.create_output_port("output_data")

        sdk.logger.info("端口创建完成，开始处理数据")

        # 主循环
        try:
            while True:
                # 非阻塞读取最新数据
                data = input_port.recv_latest()

                if data is not None:
                    # 处理数据
                    result = {"processed": True, "value": data.get("value", 0) * 2}

                    # 发送结果
                    output_port.send(result)
                    sdk.logger.debug("处理完成", input_value=data.get("value"))

                # 防止 CPU 占用过高
                time.sleep(0.01)

        except KeyboardInterrupt:
            sdk.logger.info("节点关闭")

if __name__ == '__main__':
    main()
```

## 工作流程

### 1. 初始化 SDK

```python
from nodeflow_sdk import NodeFlowSDK

# 初始化SDK，指定日志级别
sdk = NodeFlowSDK(log_level="INFO")

# SDK 自动从环境变量读取：
# - NODE_ID: 节点实例ID
# - NODE_HUB_PATH: 节点库路径
# - NODEFLOW_LOG_DIR: 日志目录
# - NODE_PARENT_WATCHDOG: 父进程监控开关
```

### 2. 获取参数

```python
# 从 YAML 配置中获取参数
simulator_host = sdk.get_param('simulator_host', 'localhost')
simulator_port = sdk.get_param('simulator_port', 5555)

# 必填参数（如果缺少会抛出异常）
required_value = sdk.require_param('required_key')
```

### 3. 创建端口

```python
# 输入端口（读取）
input_port = sdk.create_input_port('rtk_fix')

# 输出端口（写入）
output_port = sdk.create_output_port('pose_enu')

# 带 Schema 的输出端口（数据验证）
from pydantic import BaseModel

class PoseENU(BaseModel):
    x: float
    y: float
    theta: float

output_port = sdk.create_output_port('pose_enu', schema=PoseENU)
```

### 4. 数据通信

```python
# 发送数据到输出端口
output_port.send({
    'x': 100.5,
    'y': 200.3,
    'theta': 1.57
})

# 读取输入端口的最新数据（非阻塞）
data = input_port.recv_latest()
if data is not None:
    print(f"收到数据: {data}")

# 等待输入（阻塞模式，可选）
data = input_port.read_blocking(timeout=1.0)
```

### 5. 日志记录

```python
# SDK 包含结构化日志系统（自动启用）
sdk.logger.debug("调试消息", custom_field=value)
sdk.logger.info("信息消息", node_status="ready")
sdk.logger.warning("警告消息", threshold=100, actual=150)
sdk.logger.error("错误消息", exc_info=True)
sdk.logger.critical("严重消息")
```

### 6. 清理资源

```python
# 使用上下文管理器（推荐）
with NodeFlowSDK(log_level="INFO") as sdk:
    # 使用 SDK
    ...
# 自动调用 sdk.shutdown()

# 或手动关闭
sdk.shutdown()
```

## 常见模式

### 模式 1: 数据转换节点

```python
class TransformNode:
    def __init__(self, sdk):
        self.sdk = sdk
        self.input = sdk.create_input_port('input')
        self.output = sdk.create_output_port('output')

    def run(self):
        while True:
            data = self.input.recv_latest()
            if data:
                # 转换数据
                result = self.transform(data)
                self.output.send(result)
            time.sleep(0.01)

    def transform(self, data):
        # 在这里实现转换逻辑
        return data

def main():
    with NodeFlowSDK() as sdk:
        node = TransformNode(sdk)
        node.run()
```

### 模式 2: 传感器读取节点

```python
class SensorNode:
    def __init__(self, sdk):
        self.sdk = sdk
        self.sensor = self.init_sensor()
        self.rtk_output = sdk.create_output_port('rtk_fix')
        self.imu_output = sdk.create_output_port('imu_data')

    def init_sensor(self):
        # 初始化硬件
        return HardwareSensor()

    def run(self):
        try:
            while True:
                # 读取传感器
                rtk_data = self.sensor.read_rtk()
                imu_data = self.sensor.read_imu()

                # 发送数据
                if rtk_data:
                    self.rtk_output.send(rtk_data)
                if imu_data:
                    self.imu_output.send(imu_data)

                # 控制频率
                time.sleep(1.0 / 50)  # 50Hz
        except Exception as e:
            self.sdk.logger.error("传感器故障", exc_info=True)
            raise

def main():
    with NodeFlowSDK() as sdk:
        node = SensorNode(sdk)
        node.run()
```

### 模式 3: 多端口控制节点

```python
class ControlNode:
    def __init__(self, sdk):
        self.sdk = sdk
        # 多个输入
        self.pose = sdk.create_input_port('pose_enu')
        self.waypoint = sdk.create_input_port('waypoint')
        self.limits = sdk.create_input_port('limits')

        # 多个输出
        self.cmd = sdk.create_output_port('velocity_cmd')
        self.status = sdk.create_output_port('control_status')

    def run(self):
        while True:
            # 读取所有输入
            pose = self.pose.recv_latest()
            waypoint = self.waypoint.recv_latest()
            limits = self.limits.recv_latest()

            if pose and waypoint:
                # 计算控制命令
                cmd = self.compute_control(pose, waypoint, limits)
                self.cmd.send(cmd)
                self.status.send({"status": "ok"})

            time.sleep(0.01)

    def compute_control(self, pose, waypoint, limits):
        # 控制算法
        return {"v": 1.0, "omega": 0.0}
```

## 环境变量

SDK 使用以下环境变量（由框架自动设置）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `NODE_ID` | 节点实例 ID | `sim_output` |
| `NODE_HUB_PATH` | 节点库路径 | `./node-hub` |
| `NODE_SOCKET_DIR` | Socket 临时目录 | `/tmp/nodeflow` |
| `NODE_IN_*` | 输入端口 ZMQ 地址 | `ipc://...` |
| `NODE_OUT_*` | 输出端口 ZMQ 地址 | `ipc://...` |
| `NODE_PARENT_WATCHDOG` | 启用父进程监控 | `true` |
| `NODEFLOW_LOG_DIR` | 日志目录 | `/tmp/nodeflow_logs` |
| `NODE_SCHEMA_VALIDATION` | Schema 验证模式 | `off/loose/strict` |

## 错误处理

```python
from nodeflow_sdk import NodeFlowSDK

try:
    with NodeFlowSDK(log_level="INFO") as sdk:
        # 处理"必填参数缺失"
        try:
            required = sdk.require_param('important_param')
        except ValueError as e:
            sdk.logger.error("参数缺失", param_name='important_param')
            raise

        # 处理"端口创建失败"
        try:
            input_port = sdk.create_input_port('data')
        except ValueError as e:
            sdk.logger.error("端口创建失败", port_name='data')
            raise

        # 处理"数据发送异常"
        try:
            output_port = sdk.create_output_port('result')
            output_port.send({'value': 123})
        except Exception as e:
            sdk.logger.error("数据发送失败", exc_info=True)
            raise

except KeyboardInterrupt:
    print("用户中断")
except Exception as e:
    print(f"致命错误: {e}")
    exit(1)
```

## 性能考虑

1. **轮询间隔** - 使用 `time.sleep()` 控制 CPU 占用
   ```python
   while True:
       data = port.recv_latest()
       # 处理数据...
       time.sleep(0.01)  # 100Hz
   ```

2. **缓冲区大小** - 在 `node.yaml` 中配置
   ```yaml
   ports:
     outputs:
       - name: output_data
         buffer_size: 10485760  # 10MB
   ```

3. **Schema 验证** - 可选性能开销
   ```python
   # 生产环境建议关闭严格验证
   export NODE_SCHEMA_VALIDATION=off
   ```

4. **日志级别** - 减少日志开销
   ```python
   # 生产环境使用 WARNING 级别
   sdk = NodeFlowSDK(log_level="WARNING")
   ```

## 下一步

- 查看 [SDK API 参考](SDK_API_REFERENCE.md) 了解完整 API
- 查看 [SDK 最佳实践](SDK_BEST_PRACTICES.md) 学习设计模式
- 查看 [真实节点示例](../node-hub) 学习完整实现

## 获取帮助

- **日志** - 用 `nodeflow logs --follow` 查看实时日志
- **诊断** - 用 `nodeflow health check <config.yaml>` 检查配置
- **监控** - 用 `nodeflow monitor <config.yaml>` 监控缓冲区
