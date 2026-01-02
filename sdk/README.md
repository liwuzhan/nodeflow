# NodeFlow SDK

NodeFlow SDK 是一个用于构建分布式传感器-控制系统的高性能节点开发工具包。

## 快速导航

📚 **文档**

- [快速入门](../docs/SDK_GETTING_STARTED.md) - 10分钟上手NodeFlow SDK
- [API参考](../docs/SDK_API_REFERENCE.md) - 完整的API文档
- [最佳实践](../docs/SDK_BEST_PRACTICES.md) - 设计模式和性能优化
- [日志系统](../docs/STRUCTURED_LOGGING_GUIDE.md) - 结构化日志使用指南

🚀 **核心特性**

- **简单易用** - 最小化样板代码，专注业务逻辑
- **高性能** - 混合IPC（共享内存 + ZeroMQ），微秒级延迟
- **类型安全** - 可选的Pydantic Schema验证
- **结构化日志** - JSON格式日志 + 实时控制台输出
- **零配置** - 自动启用，无需手动设置

## 快速示例

```python
#!/usr/bin/env python3
from nodeflow_sdk import NodeFlowSDK
import time

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"节点 {sdk.node_id} 启动")

        # 创建端口
        input_port = sdk.create_input_port("input_data")
        output_port = sdk.create_output_port("output_data")

        # 主循环
        while True:
            data = input_port.recv_latest()
            if data:
                result = {"value": data.get("value", 0) * 2}
                output_port.send(result)
                sdk.logger.debug("处理完成", input=data)

            time.sleep(0.01)

if __name__ == '__main__':
    main()
```

## 核心 API

### SDK 初始化

```python
from nodeflow_sdk import NodeFlowSDK

# 推荐：使用上下文管理器
with NodeFlowSDK(log_level="INFO") as sdk:
    # 使用 SDK...
    pass
# 自动清理资源
```

### 参数管理

```python
# 可选参数（带默认值）
timeout = sdk.get_param('timeout', 1000)

# 必填参数（缺失时抛出异常）
api_key = sdk.require_param('api_key')
```

### 端口创建

```python
# 输入端口（读取）
input_port = sdk.create_input_port('data_input')

# 输出端口（写入）
output_port = sdk.create_output_port('data_output')

# 带Schema验证的输出端口
from pydantic import BaseModel

class Position(BaseModel):
    x: float
    y: float

output_port = sdk.create_output_port('position', schema=Position)
```

### 数据通信

```python
# 发送数据
output_port.send({'x': 100.5, 'y': 200.3})

# 读取最新数据（非阻塞）
data = input_port.recv_latest()
if data:
    print(f"收到: {data}")

# 阻塞读取（可选超时）
data = input_port.read_blocking(timeout=1.0)
```

### 日志记录

```python
# 结构化日志（自动包含JSON格式）
sdk.logger.debug("调试消息", custom_field=value)
sdk.logger.info("信息消息", node_status="ready")
sdk.logger.warning("警告消息", threshold=100)
sdk.logger.error("错误消息", exc_info=True)
sdk.logger.critical("严重消息")
```

## 模块说明

- `nodeflow_sdk.py` - SDK主类，提供节点开发核心API
- `port.py` - InputPort和OutputPort，进程间通信
- `structured_logger.py` - 结构化日志系统
- `param_parser.py` - 参数解析器
- `shared_buffer_lite.py` - 共享内存实现
- `latest_value_reader.py` - 最新值读取器

## 环境要求

- Python 3.10+
- pyzmq >= 24.0.0
- msgpack >= 1.0.0
- pydantic >= 2.0 (可选，用于Schema验证)

## 性能指标

在现代硬件上的典型性能：

| 操作 | 吞吐量 | 延迟 |
|------|--------|------|
| 简单数据发送 | >100K msg/s | <0.5ms |
| JSON 序列化 | >50K msg/s | <1ms |
| Schema 验证 | >20K msg/s | <2ms |

## 示例节点

查看 `node-hub/` 目录下的真实节点示例：

- `sim_output/` - 仿真器输出节点（多端口）
- `global_coverage/` - 路径规划节点（算法密集型）
- `track_controller/` - 轨迹控制节点（实时控制）
- `coord_transform/` - 坐标转换节点（数据转换）

## 获取帮助

- **文档** - 查看 `docs/` 目录下的完整文档
- **日志** - 使用 `nodeflow logs --follow` 查看实时日志
- **诊断** - 使用 `nodeflow health check` 检查配置
- **监控** - 使用 `nodeflow monitor` 监控缓冲区

## 许可证

NodeFlow SDK 是 NodeFlow 框架的一部分。
