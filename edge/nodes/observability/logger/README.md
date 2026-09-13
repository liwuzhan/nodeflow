# Logger 节点

数据记录/回放节点 - 类似磁带，可记录和回放任意数据流

## 功能说明

- **10 通道 I/O**：10 个输入/输出端口，支持任意类型数据
- **记录模式**：将输入数据流记录到文件
- **回放模式**：从文件读取数据并按时间顺序输出

## 节点架构

```
logger/
├── node.yaml          # 节点声明文件
├── run.py             # L3层主逻辑
├── atom.py            # L4层纯算法
├── data/recordings/   # 记录文件存储目录
└── README.md          # 本文档
```

## 端口说明

### 输入端口

| 端口名 | 类型 | 说明 |
|--------|------|------|
| `input_0` ~ `input_9` | any | 数据输入通道 0-9 |

### 输出端口

| 端口名 | 类型 | 说明 |
|--------|------|------|
| `output_0` ~ `output_9` | any | 数据输出通道 0-9 |

## 参数说明

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `mode` | string | record | 运行模式：record/playback |
| `record_name` | string | recording | 记录文件名 |
| `playback_speed` | float | 1.0 | 回放速度倍数（1.0=原速） |
| `loop_playback` | bool | false | 回放是否循环 |
| `max_records` | integer | 10 | 保留的最大记录文件数量 |

## 使用方法

### 1. 记录模式

记录 RTK 数据和控制输入：

```yaml
nodes:
  - name: logger
    package: logger
    params:
      mode: record
      record_name: "test_run"

edges:
  - from: rtk_driver.rtk_fix
    to: logger.input_0
  - from: joystick.control_input
    to: logger.input_1
```

### 2. 回放模式

回放之前的数据：

```yaml
nodes:
  - name: logger
    package: logger
    params:
      mode: playback
      playback_speed: 1.0
      loop_playback: true

edges:
  - from: logger.output_0
    to: waypoint_selector.rtk_fix
  - from: logger.output_1
    to: track_controller.control_input
```

## 数据格式

记录文件使用 Python pickle 格式保存，结构如下：

```python
[
    {
        'timestamp': 1703024780.123,
        'datetime': '2023-12-20T10:00:00',
        'channels': {
            'channel_0': {...},  # input_0 的数据
            'channel_1': {...},  # input_1 的数据
            # ...
        }
    },
    # ... 更多帧
]
```

## 注意事项

1. 记录文件保存在 `data/recordings/` 目录
2. 回放时会自动加载最新的记录文件
3. 节点退出时自动保存记录（record 模式）
