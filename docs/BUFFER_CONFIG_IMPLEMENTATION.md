# Buffer Configuration Feature - Implementation Summary

## 概述

成功实现了缓冲区配置暴露功能，允许节点开发者在 `node.yaml` 中自定义输出端口的缓冲区大小和覆盖策略。

## 实现日期

2025-12-24

## 功能特性

### 1. 配置参数

每个输出端口支持两个配置参数：

- **buffer_size** (int): 缓冲区大小（字节）
  - 默认值: 1048576 (1MB)
  - 用途: 控制共享内存缓冲区的大小
  - 适用场景: 小数据量（传感器数据、路径点）使用默认值，大数据量（激光雷达、4K摄像头）需要增加

- **conflate** (bool): 覆盖模式
  - 默认值: true
  - 用途: 控制是否使用最新值语义（覆盖旧数据）
  - 当前实现: 仅支持 true（覆盖模式），false 为未来队列模式预留

### 2. 配置方式

在 `node.yaml` 的输出端口定义中添加配置：

```yaml
outputs:
  - name: global_path
    type: planning.path
    description: 规划生成的WGS84经纬度路径点列表
    buffer_size: 1048576  # 1MB（可选，默认1MB）
    conflate: true        # 覆盖模式（可选，默认true）
```

### 3. 配置传递流程

```
node.yaml
    ↓
YAMLParser 解析
    ↓
PortDef 数据模型 (buffer_size, conflate)
    ↓
EnvBuilder 构建环境变量
    ↓
环境变量传递给节点进程
  - NODE_OUT_<port>_BUFFER_SIZE
  - NODE_OUT_<port>_CONFLATE
    ↓
OutputPort 读取环境变量
    ↓
SharedBufferLite 使用配置创建缓冲区
```

## 代码修改详情

### 1. 数据模型 (runtime/config/models.py)

修改 `PortDef` 类，添加两个新字段：

```python
@dataclass
class PortDef:
    """端口定义"""
    name: str
    type: str = "any"
    description: str = ""
    buffer_size: int = 1024 * 1024  # NEW: 缓冲区大小（字节），默认1MB
    conflate: bool = True           # NEW: 是否覆盖旧数据，默认True
```

### 2. 共享缓冲区 (sdk/shared_buffer_lite.py)

更新默认缓冲区大小：

```python
DEFAULT_SIZE = 1024 * 1024  # 从 64KB 更新为 1MB
```

### 3. 环境变量构建 (runtime/orchestrator/env_builder.py)

修改 `build_env()` 方法，为每个输出端口添加配置环境变量：

```python
# 添加buffer配置
buffer_size = getattr(output_port, 'buffer_size', 1024 * 1024)
conflate = getattr(output_port, 'conflate', True)

env[f'NODE_OUT_{port_name}_BUFFER_SIZE'] = str(buffer_size)
env[f'NODE_OUT_{port_name}_CONFLATE'] = str(conflate).lower()
```

### 4. 输出端口 (sdk/port.py)

修改 `OutputPort.__init__()` 读取环境变量配置：

```python
import os

# 从环境变量读取buffer配置
buffer_size_env = os.getenv(f'NODE_OUT_{name}_BUFFER_SIZE')
self.buffer_size = int(buffer_size_env) if buffer_size_env else 1024 * 1024

conflate_env = os.getenv(f'NODE_OUT_{name}_CONFLATE', 'true')
self.conflate = conflate_env.lower() == 'true'
```

修改 `_setup()` 使用配置的缓冲区大小：

```python
self.buffer = SharedBufferLite(self.buffer_name, size=self.buffer_size, create=True)
```

## 测试验证

### 测试文件

`tests/integration/test_buffer_config.py` - 7个综合测试

### 测试覆盖

✅ **test_portdef_default_values** - 验证 PortDef 默认值（1MB, conflate=true）
✅ **test_portdef_custom_values** - 验证 PortDef 自定义值（5MB, conflate=false）
✅ **test_env_builder_passes_buffer_config** - 验证 EnvBuilder 正确传递环境变量
✅ **test_shared_buffer_with_custom_size** - 验证 SharedBufferLite 支持不同大小（512KB, 10MB）
✅ **test_yaml_config_loading** - 验证从 node.yaml 加载配置（global_coverage 节点）
✅ **test_outputport_reads_env_config** - 验证 OutputPort 正确读取环境变量（2MB）
✅ **test_outputport_uses_defaults** - 验证 OutputPort 使用默认值（1MB）

### 测试结果

```
============================= test session starts ==============================
tests/integration/test_buffer_config.py::test_portdef_default_values PASSED
tests/integration/test_buffer_config.py::test_portdef_custom_values PASSED
tests/integration/test_buffer_config.py::test_env_builder_passes_buffer_config PASSED
tests/integration/test_buffer_config.py::test_shared_buffer_with_custom_size PASSED
tests/integration/test_buffer_config.py::test_yaml_config_loading PASSED
tests/integration/test_buffer_config.py::test_outputport_reads_env_config PASSED
tests/integration/test_buffer_config.py::test_outputport_uses_defaults PASSED
============================== 7 passed in 0.19s ===============================
```

## 配置示例

### 示例1: RTK/IMU数据（小数据量，使用默认值）

```yaml
outputs:
  - name: rtk_fix
    type: sensor.rtk
    description: RTK定位数据
    # 省略 buffer_size 和 conflate，自动使用默认值
    # buffer_size: 1048576 (1MB)
    # conflate: true
```

### 示例2: 路径规划（中等数据量，使用默认值）

```yaml
outputs:
  - name: global_path
    type: planning.path
    description: 规划的全局路径
    buffer_size: 1048576  # 1MB - 足以存储几百个路径点
    conflate: true        # 覆盖模式
```

### 示例3: 多线激光雷达（大数据量）

```yaml
outputs:
  - name: point_cloud
    type: sensor.lidar
    description: 激光雷达点云
    buffer_size: 5242880  # 5MB (5 * 1024 * 1024)
    conflate: true
```

### 示例4: 4K摄像头（超大数据量）

```yaml
outputs:
  - name: image
    type: sensor.camera
    description: 4K RGB图像
    buffer_size: 20971520  # 20MB (20 * 1024 * 1024)
    conflate: true  # 只保留最新帧
```

## Buffer大小参考表

| 数据类型               | 典型大小    | 建议Buffer大小 |
|-----------------------|------------|---------------|
| RTK 定位数据           | ~100-200 B | 默认 1MB      |
| IMU 加速度/陀螺仪      | ~50-100 B  | 默认 1MB      |
| 轨迹路径点 (100个点)   | ~3KB       | 默认 1MB      |
| 轨迹路径点 (1000个点)  | ~30KB      | 默认 1MB      |
| 单线激光雷达 (20万点)  | ~1.5MB     | 建议 2-3MB    |
| 多线激光雷达 (100万点) | ~7.5MB     | 建议 10MB     |
| 4K RGB 图像           | ~24-30MB   | 建议 30-50MB  |
| HD 图像 (1920×1080)   | ~6MB       | 建议 8-10MB   |

## 配置原则

1. **默认1MB足以满足大多数场景**（轨迹、传感器数据）
2. **多线激光雷达**: 5-10MB
3. **摄像头/高分辨率图像**: 20-50MB
4. **大型学习模型权重**: 可能需要100MB+
5. **始终预留20-30%余量**应对数据变化

## 环境变量格式

### 输出端口环境变量

- **NODE_OUT_<port_name>**: ZMQ地址 (如 `ipc:///tmp/nodeflow/node_id.port_name`)
- **NODE_OUT_<port_name>_BUFFER_SIZE**: 缓冲区大小（字节，字符串）
- **NODE_OUT_<port_name>_CONFLATE**: 覆盖模式 ("true" 或 "false"，字符串）

### 示例

```bash
NODE_OUT_global_path=ipc:///tmp/nodeflow/global_coverage_1.global_path
NODE_OUT_global_path_BUFFER_SIZE=1048576
NODE_OUT_global_path_CONFLATE=true
```

## 向后兼容性

- ✅ **完全向后兼容**: 所有现有节点无需修改即可继续工作
- ✅ **默认值**: 未配置时自动使用1MB缓冲区和覆盖模式
- ✅ **渐进式迁移**: 节点可以逐步添加配置，无需一次性修改所有节点

## 未来扩展

### 队列模式支持（conflate=false）

当前实现仅支持覆盖模式（conflate=true），未来可扩展支持队列模式：

- **conflate=true**: 覆盖模式，只保留最新值（当前实现）
- **conflate=false**: 队列模式，保留历史数据（未来扩展）

队列模式需要：
1. 实现环形缓冲区
2. 添加读写指针管理
3. 支持多消费者同步

### 动态缓冲区大小

未来可支持运行时动态调整缓冲区大小，适应不同负载情况。

## 相关文档

- `BUFFER_CONFIG_EXAMPLE.yaml` - 详细配置示例和参考表
- `node-hub/global_coverage/node.yaml` - 实际节点配置示例
- `tests/integration/test_buffer_config.py` - 测试用例

## 实现状态

✅ **功能完成**: 100%
✅ **测试通过**: 7/7
✅ **文档完成**: 100%
✅ **向后兼容**: 是

## 总结

Buffer配置功能已成功实现并通过全面测试。该功能为节点开发者提供了灵活的缓冲区配置能力，同时保持了良好的默认值和向后兼容性。现在可以支持从小数据量传感器（使用默认1MB）到大数据量设备（如4K摄像头、多线激光雷达）的各种应用场景。
