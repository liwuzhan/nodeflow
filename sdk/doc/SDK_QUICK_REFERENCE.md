# NodeFlow SDK 快速参考卡

一页纸速查表，常用API和模式。

## 基本结构

```python
#!/usr/bin/env python3
from nodeflow_sdk import NodeFlowSDK
import time

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        # 1. 获取参数
        param = sdk.get_param('key', default_value)

        # 2. 创建端口
        input = sdk.create_input_port('input')
        output = sdk.create_output_port('output')

        # 3. 主循环
        while True:
            data = input.recv_latest()
            if data:
                result = process(data)
                output.send(result)
            time.sleep(0.01)

if __name__ == '__main__':
    main()
```

## SDK 初始化

```python
# 推荐：上下文管理器
with NodeFlowSDK(log_level="INFO") as sdk:
    ...  # 自动清理

# 手动管理
sdk = NodeFlowSDK(log_level="INFO")
try:
    ...
finally:
    sdk.shutdown()
```

## 参数

```python
# 可选参数
value = sdk.get_param('key', default)

# 必填参数
value = sdk.require_param('key')  # 抛出 ValueError 如果缺失

# 访问所有参数
params = sdk.params  # Dict[str, Any]
```

## 端口

### 创建

```python
# 输入
input = sdk.create_input_port('port_name')

# 输出
output = sdk.create_output_port('port_name')

# 带Schema
from pydantic import BaseModel
class Data(BaseModel):
    value: float
output = sdk.create_output_port('port_name', schema=Data)
```

### 读取

```python
# 非阻塞（推荐）
data = input.recv_latest()
if data:
    print(data)

# 阻塞
data = input.read_blocking(timeout=1.0)

# 检查连接
if input.is_connected():
    ...
```

### 写入

```python
# 发送字典
output.send({'key': 'value'})

# 发送Pydantic对象
data = Data(value=42.0)
output.send(data)
```

## 日志

```python
# 5个级别
sdk.logger.debug("msg", field=value)
sdk.logger.info("msg", field=value)
sdk.logger.warning("msg", field=value)
sdk.logger.error("msg", exc_info=True, field=value)
sdk.logger.critical("msg", field=value)

# 日志文件位置
# /tmp/nodeflow_logs/<node_id>.jsonl
```

## 常用模式

### 多输入处理

```python
input1 = sdk.create_input_port('input1')
input2 = sdk.create_input_port('input2')

while True:
    data1 = input1.recv_latest()
    data2 = input2.recv_latest()

    if data1 and data2:
        result = combine(data1, data2)
        output.send(result)

    time.sleep(0.01)
```

### 条件输出

```python
while True:
    data = input.recv_latest()
    if data:
        if data['type'] == 'A':
            output_a.send(data)
        else:
            output_b.send(data)
    time.sleep(0.01)
```

### 状态保持

```python
class Node:
    def __init__(self, sdk):
        self.sdk = sdk
        self.state = {}  # 保持状态
        self.count = 0

    def run(self):
        while True:
            data = self.input.recv_latest()
            if data:
                self.state[data['id']] = data
                self.count += 1
            time.sleep(0.01)
```

### 错误重试

```python
def send_with_retry(output, data, retries=3):
    for i in range(retries):
        try:
            output.send(data)
            return True
        except Exception as e:
            sdk.logger.warning(f"重试 {i+1}/{retries}")
            time.sleep(2 ** i)
    return False
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `NODE_ID` | 节点ID（自动设置） |
| `NODEFLOW_LOG_DIR` | 日志目录（默认 /tmp/nodeflow_logs） |
| `NODE_SCHEMA_VALIDATION` | off/loose/strict |
| `NODE_PARENT_WATCHDOG` | true/false |

## node.yaml 示例

```yaml
name: my_node
version: "1.0"
description: "节点描述"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

ports:
  inputs:
    - name: input_data
      type: sensor.data
  outputs:
    - name: output_data
      type: processed.data
      buffer_size: 1048576  # 1MB
      conflate: true

params:
  sample_rate:
    type: float
    default: 50.0
  enable_filter:
    type: bool
    default: false
```

## CLI工具

```bash
# 查看日志
nodeflow logs --follow

# 查看特定节点
nodeflow logs --node sim_output

# 只看错误
nodeflow logs --level ERROR

# 详细信息
nodeflow logs --detailed

# 健康检查
nodeflow health check config.yaml

# 监控缓冲区
nodeflow monitor config.yaml
```

## 性能建议

✅ 使用合理的轮询间隔：`time.sleep(0.01)` (100Hz)
✅ 生产环境日志级别：`log_level="WARNING"`
✅ 禁用Schema验证：`export NODE_SCHEMA_VALIDATION=off`
✅ 批量发送数据减少网络调用
✅ 使用上下文管理器自动清理资源

❌ 避免无延迟的while True循环（CPU占用100%）
❌ 避免在主循环中阻塞操作（使用线程）
❌ 避免过度日志记录（每次循环都debug）

## 故障排查

| 问题 | 检查 |
|------|------|
| 端口创建失败 | NODE_IN_*/NODE_OUT_* 环境变量 |
| 读不到数据 | 上游节点是否运行？缓冲区是否存在？ |
| 性能低 | 日志级别？Schema验证？轮询间隔？ |
| 日志不输出 | NODEFLOW_LOG_DIR 权限？日志级别？ |

## 文档链接

- 📖 [快速入门](SDK_GETTING_STARTED.md)
- 📘 [API参考](SDK_API_REFERENCE.md)
- 📗 [最佳实践](SDK_BEST_PRACTICES.md)
- 📕 [日志系统](STRUCTURED_LOGGING_GUIDE.md)
