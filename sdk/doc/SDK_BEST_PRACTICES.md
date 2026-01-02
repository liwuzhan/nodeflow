# NodeFlow SDK 最佳实践

经过实战验证的设计模式、性能优化技巧和避免常见陷阱的指南。

## 目录

- [架构设计](#架构设计)
- [性能优化](#性能优化)
- [错误处理](#错误处理)
- [测试](#测试)
- [常见陷阱](#常见陷阱)
- [实战案例](#实战案例)

---

## 架构设计

### 模式 1: 分离关注点

将节点逻辑分为三层：

```python
class MyNode:
    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self._init_ports()
        self._init_state()
        self._init_hardware()

    def _init_ports(self):
        """创建端口（框架相关）"""
        self.input = self.sdk.create_input_port('input')
        self.output = self.sdk.create_output_port('output')

    def _init_state(self):
        """初始化状态（业务逻辑）"""
        self.last_value = None
        self.processed_count = 0

    def _init_hardware(self):
        """初始化硬件（外部依赖）"""
        self.sensor = HardwareSensor()

    def run(self):
        """主循环"""
        while True:
            self._read_inputs()
            self._process()
            self._write_outputs()
            self._maintain()

    def _read_inputs(self):
        """读取输入数据"""
        self.data = self.input.recv_latest()

    def _process(self):
        """处理业务逻辑"""
        if self.data:
            self.result = self.algorithm(self.data)
            self.processed_count += 1

    def _write_outputs(self):
        """发送输出数据"""
        if self.result:
            self.output.send(self.result)

    def _maintain(self):
        """维护循环（日志、延迟等）"""
        time.sleep(0.01)
        if self.processed_count % 100 == 0:
            self.sdk.logger.debug("处理进度",
                count=self.processed_count)

    def algorithm(self, data):
        # 核心算法，易于单元测试
        return data
```

**优点**

- 易于理解、测试和维护
- 外部依赖清晰
- 业务逻辑独立于框架

### 模式 2: 可配置化处理

利用参数使节点灵活适应不同场景：

```python
class FlexibleNode:
    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 从参数获取配置，带默认值
        self.sample_rate = sdk.get_param('sample_rate', 50.0)
        self.buffer_size = sdk.get_param('buffer_size', 100)
        self.enable_filter = sdk.get_param('enable_filter', False)
        self.filter_alpha = sdk.get_param('filter_alpha', 0.2)

        # 必填参数（缺失会报错）
        self.sensor_id = sdk.require_param('sensor_id')

        self.sdk.logger.info("节点配置",
            sample_rate=self.sample_rate,
            buffer_size=self.buffer_size,
            enable_filter=self.enable_filter,
            sensor_id=self.sensor_id)

    def run(self):
        cycle_time = 1.0 / self.sample_rate
        while True:
            data = self.input.recv_latest()
            if data:
                if self.enable_filter:
                    data = self.filter(data)
                self.output.send(data)
            time.sleep(cycle_time)
```

**对应的 YAML 配置**

```yaml
nodes:
  - id: flexible_node
    package: my_node
    params:
      sensor_id: "sensor_001"      # 必填
      sample_rate: 100.0            # 可选
      buffer_size: 200
      enable_filter: true
      filter_alpha: 0.15
```

### 模式 3: 状态机模式

用于处理复杂的节点生命周期：

```python
from enum import Enum

class NodeState(Enum):
    INIT = "init"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    SHUTDOWN = "shutdown"

class StatefulNode:
    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.state = NodeState.INIT
        self.error_count = 0
        self.max_errors = 3

    def run(self):
        try:
            while self.state != NodeState.SHUTDOWN:
                if self.state == NodeState.INIT:
                    self._handle_init()
                elif self.state == NodeState.READY:
                    self._handle_ready()
                elif self.state == NodeState.RUNNING:
                    self._handle_running()
                elif self.state == NodeState.ERROR:
                    self._handle_error()

                time.sleep(0.01)
        finally:
            self.state = NodeState.SHUTDOWN
            self._cleanup()

    def _handle_init(self):
        """初始化阶段"""
        try:
            self.sensor = HardwareSensor()
            self.port = self.sdk.create_input_port('data')
            self.state = NodeState.READY
            self.sdk.logger.info("初始化完成")
        except Exception as e:
            self.state = NodeState.ERROR
            self.sdk.logger.error("初始化失败", exc_info=True)

    def _handle_ready(self):
        """就绪阶段"""
        # 等待外部触发
        data = self.port.recv_latest()
        if data:
            self.state = NodeState.RUNNING

    def _handle_running(self):
        """运行阶段"""
        try:
            data = self.sensor.read()
            self.process(data)
            self.error_count = 0  # 重置错误计数
        except Exception as e:
            self.error_count += 1
            self.sdk.logger.warning("处理错误",
                error_count=self.error_count)

            if self.error_count >= self.max_errors:
                self.state = NodeState.ERROR

    def _handle_error(self):
        """错误恢复阶段"""
        self.sdk.logger.error("节点进入错误状态，尝试恢复")
        time.sleep(1.0)  # 等待后重试
        self.error_count = 0
        self.state = NodeState.READY

    def _cleanup(self):
        """清理资源"""
        self.sdk.logger.info("清理资源")
```

---

## 性能优化

### 1. 轮询间隔优化

**不推荐** - 不必要的繁忙等待

```python
while True:
    data = port.recv_latest()
    if data:
        process(data)
    # 无延迟，CPU 占用 100%
```

**推荐** - 合理的轮询间隔

```python
# 根据预期频率计算循环周期
sample_rate = sdk.get_param('sample_rate', 50.0)  # 50Hz
cycle_time = 1.0 / sample_rate  # 20ms

while True:
    data = port.recv_latest()
    if data:
        process(data)
    time.sleep(cycle_time)
```

### 2. 批量处理

**单条处理** - 频繁的 send 调用开销

```python
for item in data_list:
    output.send({"item": item})  # N 次网络调用
```

**批量处理** - 合并后一次发送

```python
# 累积数据
batch = []
for item in data_list:
    batch.append(item)
    if len(batch) >= 100:  # 达到阈值
        output.send({"batch": batch})
        batch = []

# 最后发送剩余数据
if batch:
    output.send({"batch": batch})
```

### 3. 缓冲区大小调优

**默认（1MB）** - 适合大多数场景

```yaml
ports:
  outputs:
    - name: output
      buffer_size: 1048576  # 1MB
```

**高吞吐量** - 增加缓冲区防止丢失

```yaml
ports:
  outputs:
    - name: high_frequency_output
      buffer_size: 52428800  # 50MB
```

**低延迟** - 使用较小缓冲区

```yaml
ports:
  outputs:
    - name: command_output
      buffer_size: 262144  # 256KB
```

### 4. 日志级别管理

**开发环境** - 详细日志便于调试

```python
sdk = NodeFlowSDK(log_level="DEBUG")
sdk.logger.debug("详细信息", x=10, y=20)  # 开销可接受
```

**生产环境** - 减少日志开销

```python
sdk = NodeFlowSDK(log_level="WARNING")
# 只记录警告和错误，性能最优
```

### 5. Schema 验证优化

**开发环境** - 启用验证发现问题

```bash
export NODE_SCHEMA_VALIDATION=strict
```

**生产环境** - 禁用验证提升性能

```bash
export NODE_SCHEMA_VALIDATION=off
```

### 性能基准

在现代硬件上的典型性能：

| 操作 | 吞吐量 | 延迟 |
|------|--------|------|
| 简单数据发送（无验证） | >100K msg/s | <0.5ms |
| JSON 序列化 | >50K msg/s | <1ms |
| Schema 验证（loose） | >20K msg/s | <2ms |
| Schema 验证（strict） | >15K msg/s | <3ms |

---

## 错误处理

### 1. 分类处理不同错误

```python
def run(self):
    while True:
        try:
            data = self.input.recv_latest()
            if data:
                self.process(data)

        except KeyboardInterrupt:
            # 用户中断 - 正常退出
            self.sdk.logger.info("用户中断")
            break

        except ValueError as e:
            # 数据验证错误 - 记录但继续
            self.sdk.logger.warning("数据验证失败",
                error=str(e),
                data=data)

        except ConnectionError as e:
            # 连接错误 - 尝试重连
            self.sdk.logger.error("连接丢失", exc_info=True)
            self._reconnect()

        except Exception as e:
            # 未知错误 - 记录完整堆栈
            self.sdk.logger.critical("未知错误", exc_info=True)
            break

        finally:
            time.sleep(0.01)
```

### 2. 重试机制

```python
def send_with_retry(self, data, max_retries=3):
    """发送数据，失败时重试"""
    for attempt in range(max_retries):
        try:
            self.output.send(data)
            return True
        except Exception as e:
            self.sdk.logger.warning("发送失败",
                attempt=attempt + 1,
                error=str(e))
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
    return False
```

### 3. 优雅降级

```python
def run(self):
    primary_input = self.sdk.create_input_port('primary')
    fallback_input = self.sdk.create_input_port('fallback')

    while True:
        # 优先尝试主输入
        data = primary_input.recv_latest()

        if not data:
            # 主输入无数据，使用备用
            data = fallback_input.recv_latest()

        if data:
            self.process(data)
        else:
            self.sdk.logger.debug("等待数据")

        time.sleep(0.01)
```

---

## 测试

### 单元测试

```python
import unittest
from unittest.mock import Mock, patch

class TestMyNode(unittest.TestCase):
    def setUp(self):
        """测试前准备"""
        self.sdk = Mock()
        self.sdk.node_id = "test_node"
        self.sdk.get_param = Mock(return_value={})
        self.sdk.logger = Mock()

    def test_initialization(self):
        """测试节点初始化"""
        node = MyNode(self.sdk)
        self.assertIsNotNone(node)
        self.sdk.logger.info.assert_called()

    def test_data_processing(self):
        """测试数据处理"""
        input_data = {'x': 10, 'y': 20}
        expected_output = {'x': 20, 'y': 40}  # 翻倍

        node = MyNode(self.sdk)
        output = node.process(input_data)

        self.assertEqual(output, expected_output)

    def test_error_handling(self):
        """测试错误处理"""
        invalid_data = {'x': 'invalid'}

        node = MyNode(self.sdk)
        with self.assertRaises(ValueError):
            node.process(invalid_data)

if __name__ == '__main__':
    unittest.main()
```

### 集成测试

```python
# tests/test_node_integration.py
import os
import time
import sys
from pathlib import Path

# 设置环境变量
os.environ['NODE_ID'] = 'test_node'
os.environ['NODEFLOW_LOG_DIR'] = '/tmp/test_logs'

from nodeflow_sdk import NodeFlowSDK
from my_node import MyNode

def test_node_with_real_sdk():
    """用真实 SDK 测试节点"""
    with NodeFlowSDK() as sdk:
        # 创建测试用的端口（需要框架运行）
        input_port = sdk.create_input_port('test_input')
        output_port = sdk.create_output_port('test_output')

        # 测试发送和接收
        test_data = {'value': 42}
        output_port.send(test_data)

        time.sleep(0.1)
        received = input_port.recv_latest()

        assert received == test_data
        print("✓ 集成测试通过")
```

---

## 常见陷阱

### 陷阱 1: 堵塞主循环

**不推荐** - 某个操作堵塞会影响整个节点

```python
while True:
    data = input.recv_latest()
    if data:
        # ❌ 这里如果耗时 5 秒，会错过其他数据
        result = expensive_operation(data)  # 5 秒
        output.send(result)
    time.sleep(0.01)
```

**推荐** - 使用后台线程处理耗时操作

```python
import threading
import queue

self.work_queue = queue.Queue()

def _process_worker():
    while True:
        data = self.work_queue.get()
        if data is None:  # 停止信号
            break
        result = expensive_operation(data)
        self.output.send(result)

# 启动处理线程
worker_thread = threading.Thread(target=_process_worker, daemon=True)
worker_thread.start()

def run(self):
    while True:
        data = input.recv_latest()
        if data:
            # ✅ 快速入队，不堵塞主循环
            self.work_queue.put(data)
        time.sleep(0.01)
```

### 陷阱 2: 忘记关闭资源

**不推荐** - 资源泄漏

```python
sdk = NodeFlowSDK()
port = sdk.create_output_port('data')
# ... 使用 ...
# ❌ 忘记关闭，文件和 socket 仍然打开
```

**推荐** - 使用上下文管理器

```python
with NodeFlowSDK() as sdk:  # ✅ 自动 cleanup
    port = sdk.create_output_port('data')
    # ... 使用 ...
# 自动调用 sdk.shutdown()
```

### 陷阱 3: 不正确的日志级别

**不推荐** - 过度日志记录

```python
while True:
    sdk.logger.debug("循环迭代")  # ❌ 每 10ms 一条，太频繁
    data = input.recv_latest()
    time.sleep(0.01)
```

**推荐** - 有选择性地记录

```python
loop_count = 0
while True:
    data = input.recv_latest()
    if data:
        sdk.logger.debug("收到数据", size=len(data))
        process(data)

    # 周期性日志
    loop_count += 1
    if loop_count % 1000 == 0:  # 每秒一条
        sdk.logger.debug("运行中", loop_count=loop_count)

    time.sleep(0.01)
```

### 陷阱 4: Schema 验证性能

**不推荐** - 严格验证每条消息

```bash
export NODE_SCHEMA_VALIDATION=strict
```

在生产环境每条消息都会验证，性能下降 50%+。

**推荐** - 根据环境调整

```bash
# 开发环境：发现问题
export NODE_SCHEMA_VALIDATION=strict

# 生产环境：性能优先
export NODE_SCHEMA_VALIDATION=off
```

### 陷阱 5: 忽视参数默认值

**不推荐** - 硬编码参数

```python
sample_rate = 50.0
buffer_size = 1000
timeout = 2000

# ... 无法通过 YAML 配置 ...
```

**推荐** - 使用参数系统

```python
sample_rate = sdk.get_param('sample_rate', 50.0)
buffer_size = sdk.get_param('buffer_size', 1000)
timeout = sdk.get_param('timeout', 2000)

# ... 可通过 YAML 灵活配置 ...
```

---

## 实战案例

### 案例 1: 传感器融合节点

完整的多输入数据融合示例：

```python
class SensorFusionNode:
    def __init__(self, sdk):
        self.sdk = sdk

        # 多个输入源
        self.gps_input = sdk.create_input_port('gps_fix')
        self.imu_input = sdk.create_input_port('imu_data')
        self.lidar_input = sdk.create_input_port('lidar_data')

        # 输出
        self.fusion_output = sdk.create_output_port('fused_state')

        # 融合参数
        self.gps_weight = sdk.get_param('gps_weight', 0.5)
        self.imu_weight = sdk.get_param('imu_weight', 0.3)
        self.lidar_weight = sdk.get_param('lidar_weight', 0.2)

    def run(self):
        while True:
            gps = self.gps_input.recv_latest()
            imu = self.imu_input.recv_latest()
            lidar = self.lidar_input.recv_latest()

            if gps and imu and lidar:
                # 数据对齐和融合
                fused = self.fuse_data(gps, imu, lidar)
                self.fusion_output.send(fused)

            time.sleep(0.01)

    def fuse_data(self, gps, imu, lidar):
        """卡尔曼滤波数据融合"""
        return {
            'x': (gps['x'] * self.gps_weight +
                  imu['x'] * self.imu_weight +
                  lidar['x'] * self.lidar_weight),
            # ... 其他字段
        }
```

### 案例 2: 控制命令生成器

```python
class ControlCommandNode:
    def __init__(self, sdk):
        self.sdk = sdk

        # 输入
        self.path = sdk.create_input_port('path')
        self.pose = sdk.create_input_port('pose')
        self.limits = sdk.create_input_port('limits')

        # 输出
        self.cmd = sdk.create_output_port('velocity_cmd')

        # 状态
        self.current_waypoint_idx = 0
        self.last_error = 0.0

    def run(self):
        while True:
            path_data = self.path.recv_latest()
            pose_data = self.pose.recv_latest()
            limits_data = self.limits.recv_latest()

            if path_data and pose_data:
                cmd = self.compute_command(
                    path_data,
                    pose_data,
                    limits_data
                )
                self.cmd.send(cmd)

                self.sdk.logger.debug("控制命令",
                    linear_v=cmd['v'],
                    angular_w=cmd['omega'],
                    waypoint_idx=self.current_waypoint_idx)

            time.sleep(0.02)  # 50Hz

    def compute_command(self, path, pose, limits):
        """纯追踪控制算法"""
        # 选择下一个路径点
        waypoint = path['waypoints'][self.current_waypoint_idx]

        # 计算偏差
        error = self.compute_error(pose, waypoint)

        # 应用控制律
        v = limits['max_speed']
        omega = self.pid_control(error)

        return {'v': v, 'omega': omega}
```

---

## 检查清单

部署节点前的检查清单：

- [ ] 已使用 `with NodeFlowSDK() as sdk:` 管理资源
- [ ] 已为所有参数提供默认值
- [ ] 已添加错误处理和重试机制
- [ ] 已优化轮询间隔，避免 CPU 占用过高
- [ ] 已添加关键事件的日志记录
- [ ] 已测试极限情况（缺失数据、超时等）
- [ ] 已测试长时间运行（>1 小时）
- [ ] 已优化缓冲区大小
- [ ] 已配置正确的日志级别
- [ ] 已在生产环境关闭 Schema 验证

---

**相关资源**

- [快速入门](SDK_GETTING_STARTED.md)
- [API 参考](SDK_API_REFERENCE.md)
- [日志系统](STRUCTURED_LOGGING_GUIDE.md)
- [真实节点](../node-hub)
