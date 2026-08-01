# RTK驱动节点 - 文件总结

## 📦 项目结构

```
node-hub/rtk_driver/
├── 📄 node.yaml                    # 节点清单（必需）
├── 🐍 run.py                       # 节点主程序（可执行）
├── 📚 nmea_parser.py               # NMEA解析库
├── 🔌 device_interface.py          # 通信接口库
├── 🧪 test_serial.py               # 串口测试工具
├── 📖 README.md                    # 完整文档
├── ⚡ QUICKSTART.md                # 快速开始（推荐先读这个）
├── 🔧 INTEGRATION_GUIDE.md         # 集成指南
└── 📝 FILES_SUMMARY.md             # 本文件

examples/
└── rtk_test.yaml                   # 测试配置文件
```

## 📋 文件清单

### 核心文件（必需）

#### 1. **node.yaml** (2.6 KB)
**用途**: NodeFlow节点清单定义

**内容**:
- 节点基本信息（名称、版本、描述）
- 输出端口定义（rtk_fix: sensor.rtk）
- 15个可配置参数
- 启动配置（Python 3 + run.py）

**何时需要**:
- 在runtime.yaml中引用此节点时自动读取
- 定义节点的对外接口

#### 2. **run.py** (13 KB, 可执行)
**用途**: RTK驱动节点的主程序

**主要类**: `RTKDriverNode`

**主要方法**:
- `setup()` - 连接RTK设备，配置输出
- `loop()` - 主循环：读取、解析、输出数据
- `cleanup()` - 清理资源

**生命周期**:
```
RTKDriverNode()
    ↓
setup()          # 连接设备
    ↓
loop()           # 重复调用，直到程序终止
    ↓
cleanup()        # 关闭设备
```

### 库文件

#### 3. **nmea_parser.py** (14 KB)
**用途**: NMEA 0183消息解析库

**主要类**: `NMEAParser`

**支持的消息**:
- `$KSXT` - 集成消息（位置+姿态+速度+NEU）
- `$GPGGA` - GPS固定数据
- `$GPRMC` - 推荐最小数据
- `$GPTHS` - 航向信息

**核心方法**:
| 方法 | 用途 |
|------|------|
| `validate_checksum()` | 验证校验和 |
| `parse()` | 自动识别并解析消息 |
| `parse_ksxt()` | 解析$KSXT消息 |
| `parse_gpgga()` | 解析$GPGGA消息 |
| `parse_gprmc()` | 解析$GPRMC消息 |

**关键特性**:
- ✅ 校验和验证
- ✅ 坐标格式转换（NMEA -> 十进制度）
- ✅ 时间戳解析
- ✅ 航向坐标系转换（北向 -> 数学坐标系）

#### 4. **device_interface.py** (9.6 KB)
**用途**: 设备通信接口库

**支持的接口**:
| 类 | 协议 | 使用场景 |
|----|------|----------|
| `SerialInterface` | UART/USB转串 | 直连RTK设备（推荐） |
| `TCPInterface` | TCP网络 | 网络连接的RTK |
| `UDPInterface` | UDP网络 | 单向数据传输 |

**基类**: `DeviceInterface` (抽象)

**核心方法**:
```python
connect()        # 建立连接
disconnect()     # 关闭连接
is_connected()   # 检查连接状态
read_line()      # 读取一行数据
write()          # 写入数据/命令
```

**工厂函数**:
```python
device = create_interface(config)  # 根据config自动选择
```

### 工具文件

#### 5. **test_serial.py** (5.3 KB, 可执行)
**用途**: 快速验证RTK串口连接

**用法**:
```bash
python3 test_serial.py [串口] [波特率]
python3 test_serial.py /dev/ttyUSB0 115200
```

**输出**:
- 原始NMEA消息（前3条）
- 第一条有效数据的详细信息
- 统计信息（总消息数、有效消息、错误）
- 消息类型分布

**何时使用**:
- 首次连接RTK设备时
- 诊断连接问题
- 验证波特率设置

### 文档文件

#### 6. **README.md** (9.7 KB) 📖 完整参考
**内容**:
- 功能特性（8个✅）
- 输出数据格式说明
- 所有15个参数详解
- 4个完整使用示例
- 支持的NMEA消息说明
- 硬件连接指南
- 故障排查（5个常见问题）
- 性能指标表
- 坐标系说明

**适合**: 深入了解功能、参数调优、故障排查

#### 7. **QUICKSTART.md** (6.0 KB) ⚡ 新手入门
**内容**:
- 5分钟快速测试（8个步骤）
- 验证检查清单
- 5个常见问题Q&A
- 下一步建议

**适合**: 第一次使用，快速上手

#### 8. **INTEGRATION_GUIDE.md** (已创建) 🔧 系统集成
**内容**:
- 4个模块详细说明
- 4个集成步骤
- 3个完整集成场景
- 参数调优指南
- 故障排查清单
- API参考

**适合**: 集成到现有系统、开发自定义节点

#### 9. **FILES_SUMMARY.md** (本文件) 📝 导航
**内容**: 文件用途、内容、使用场景

**适合**: 快速了解项目结构

### 配置文件

#### 10. **rtk_test.yaml** (在examples/目录)
**用途**: 测试配置文件

**包含**:
- RTK驱动节点配置
- RTK滤波节点
- 坐标转换网关
- 轨迹可视化节点

**使用**:
```bash
python3 -m runtime.main examples/rtk_test.yaml
```

## 🔍 如何选择文件

### 我想快速开始
1. 阅读: [QUICKSTART.md](QUICKSTART.md) ⚡
2. 运行: `python3 test_serial.py /dev/ttyUSB0`
3. 测试: `python3 -m runtime.main examples/rtk_test.yaml`

### 我想了解完整功能
1. 阅读: [README.md](README.md) 📖
2. 参考: [FILES_SUMMARY.md](FILES_SUMMARY.md)
3. 查看: node.yaml 中的所有参数

### 我想集成到系统
1. 阅读: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) 🔧
2. 参考: 3个集成场景示例
3. 调整: rtk_test.yaml 为生产配置

### 我想开发自定义节点
1. 学习: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) 中的API参考
2. 参考: nmea_parser.py 中的数据格式
3. 参考: run.py 中的节点实现模式

### 我遇到了问题
1. 查看: [README.md](README.md) 中的故障排查
2. 运行: `python3 test_serial.py` 诊断连接
3. 查看: `/tmp/rtk_raw.log` 原始数据

## 📊 代码统计

| 文件 | 行数 | 大小 | 类型 |
|------|------|------|------|
| run.py | ~400 | 13 KB | Python (可执行) |
| nmea_parser.py | ~450 | 14 KB | Python (库) |
| device_interface.py | ~350 | 9.6 KB | Python (库) |
| test_serial.py | ~180 | 5.3 KB | Python (工具) |
| node.yaml | ~80 | 2.6 KB | YAML |
| **总计代码** | **~1380** | **~44 KB** | - |
| README.md | ~400 | 9.7 KB | Markdown |
| QUICKSTART.md | ~200 | 6.0 KB | Markdown |
| INTEGRATION_GUIDE.md | ~350 | TBD | Markdown |
| **总计文档** | **~950** | **~16 KB** | - |

## 🏗️ 模块依赖关系

```
┌─────────────────────────────────────────┐
│         run.py (节点主程序)              │
├─────────────────────────────────────────┤
│  ├─ nmea_parser.py (NMEA消息解析)      │
│  │   └─ 标准库: re, math, datetime     │
│  │                                      │
│  ├─ device_interface.py (通信接口)     │
│  │   └─ 外部库: serial, socket         │
│  │                                      │
│  └─ SDK (nodeflow_sdk)                  │
│      └─ 日志、端口、参数管理           │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│      test_serial.py (测试工具)           │
├─────────────────────────────────────────┤
│  ├─ device_interface.py                 │
│  └─ nmea_parser.py                      │
└─────────────────────────────────────────┘
```

## 📦 依赖列表

**外部依赖**:
```
pyserial >= 3.5          # 串口通信
```

**标准库**:
```
re                       # 正则表达式
math                     # 数学函数
time                     # 时间处理
datetime                 # 日期时间
socket                   # TCP/UDP通信
pathlib                  # 路径处理
```

**NodeFlow SDK** (内部):
```
sdk.nodeflow_sdk         # 节点框架
```

## 🚀 快速命令参考

### 初始化
```bash
cd node-hub/rtk_driver
python3 test_serial.py /dev/ttyUSB0 115200
```

### 测试
```bash
python3 -m runtime.main ../../examples/rtk_test.yaml
```

### 查看日志
```bash
nodeflow logs -n rtk_sensor --follow
```

### 查看原始数据
```bash
tail -f /tmp/rtk_raw.log
```

### 修改配置
```bash
nano ../../examples/rtk_test.yaml
```

## 📚 相关文档链接

- [NodeFlow项目总览](../../docs/PROJECT_OVERVIEW_20260102.md)
- [SDK快速开始](../../sdk/doc/SDK_GETTING_STARTED.md)
- [坐标转换节点](../coord_transform/README.md)
- [RTK滤波节点](../rtk_filter/README.md)
- [节点开发规范](../../docs/节点开发规范.md)

## ✅ 使用检查清单

使用本RTK驱动节点时确保：

- [ ] 已安装pyserial: `pip install pyserial`
- [ ] RTK设备已连接
- [ ] 串口设备有读权限: `ls -l /dev/ttyUSB0`
- [ ] 波特率设置正确（通常115200）
- [ ] 已阅读QUICKSTART.md（5分钟快速入门）
- [ ] 已运行test_serial.py验证连接
- [ ] 理解输出数据格式（见README.md）
- [ ] 参数配置符合应用需求

## 📝 开发者笔记

**关键设计决策**:

1. **NMEA消息优先级**: $KSXT > $GPGGA+GPRMC+GPTHS
   - 原因: KSXT包含最完整的数据，一条消息足够

2. **航向坐标系转换**: 自动从北向(0°)转换为数学坐标系(东=0)
   - 原因: 与下游控制节点坐标系统一

3. **质量标识统一**: 多个质量字段统一为0-3的RTK质量代码
   - 原因: 简化下游节点的数据处理

4. **通信接口抽象**: 统一的DeviceInterface接口支持多种通信方式
   - 原因: 易于扩展（如NTRIP、蓝牙等）

5. **数据验证**: 校验和验证 + 坐标范围检查
   - 原因: 确保数据质量

**扩展点**:

- 新增NMEA消息支持: 在nmea_parser.py中添加parse_xxx()方法
- 新增通信方式: 在device_interface.py中继承DeviceInterface
- 新增数据处理: 在run.py中的_apply_smoothing()方法前后添加处理
- 新增输出格式: 修改_build_output_packet()方法

## 📞 支持和反馈

- 遇到问题？查看README.md的故障排查部分
- 需要定制功能？参考INTEGRATION_GUIDE.md中的API参考
- 有改进建议？提交GitHub Issue

---

**最后更新**: 2026-01-21
**项目状态**: ✅ 生产就绪
**文档版本**: 1.0
