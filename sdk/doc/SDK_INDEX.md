# NodeFlow SDK 文档索引

NodeFlow SDK 的完整文档体系。根据你的需求选择合适的文档开始。

## 🚀 新手上路

| 文档 | 用途 | 时间 |
|------|------|------|
| [快速入门](SDK_GETTING_STARTED.md) | 了解SDK基础和写出第一个节点 | 15分钟 |
| [快速参考](SDK_QUICK_REFERENCE.md) | 一页纸速查表 | 5分钟 |
| [SDK README](../sdk/README.md) | SDK模块总览 | 10分钟 |

## 📚 深入学习

| 文档 | 覆盖内容 |
|------|---------|
| [API参考](SDK_API_REFERENCE.md) | NodeFlowSDK、InputPort、OutputPort、StructuredLogger 的完整API |
| [最佳实践](SDK_BEST_PRACTICES.md) | 架构设计、性能优化、错误处理、测试、常见陷阱 |
| [日志系统](STRUCTURED_LOGGING_GUIDE.md) | 结构化日志、CLI工具、查询过滤 |

## 🎯 按使用场景

### 我想快速写一个节点

1. 读 [快速入门](SDK_GETTING_STARTED.md) 的"最小节点示例"
2. 查 [快速参考](SDK_QUICK_REFERENCE.md) 找API用法
3. 参考 `node-hub/` 下的真实节点示例

### 我想优化节点性能

1. 阅读 [最佳实践 - 性能优化](SDK_BEST_PRACTICES.md#性能优化)
2. 查看性能基准和优化建议
3. 用 `nodeflow logs` 和 `nodeflow monitor` 诊断

### 我想debug节点问题

1. 查 [日志系统](STRUCTURED_LOGGING_GUIDE.md) 了解日志工具
2. 用 `nodeflow logs --node <node_id> --follow` 实时查看
3. 用 `nodeflow logs --level ERROR --detailed` 查看详细错误
4. 参考 [最佳实践 - 错误处理](SDK_BEST_PRACTICES.md#错误处理)

### 我在处理复杂场景

1. 阅读 [最佳实践 - 架构设计](SDK_BEST_PRACTICES.md#架构设计)
2. 了解三种常用设计模式
3. 查 [常见陷阱](SDK_BEST_PRACTICES.md#常见陷阱) 避免问题
4. 看 [实战案例](SDK_BEST_PRACTICES.md#实战案例) 学习完整实现

### 我需要快速查一个API

1. 用 [快速参考](SDK_QUICK_REFERENCE.md) 一页纸快速查询
2. 或查 [API参考](SDK_API_REFERENCE.md) 获得详细说明

## 📖 文档结构

```
docs/
├── SDK_GETTING_STARTED.md          # ⭐ 从这里开始
│   ├── 概述
│   ├── 最小节点示例
│   ├── 工作流程
│   ├── 常见模式
│   ├── 环境变量
│   ├── 错误处理
│   └── 性能考虑
│
├── SDK_API_REFERENCE.md            # 完整API文档
│   ├── NodeFlowSDK
│   │   ├── 初始化
│   │   ├── 方法列表
│   │   └── 属性
│   ├── InputPort
│   │   ├── recv_latest()
│   │   ├── read_blocking()
│   │   └── 其他方法
│   ├── OutputPort
│   │   ├── send()
│   │   ├── 其他方法
│   │   └── 属性
│   ├── StructuredLogger
│   │   ├── debug/info/warning/error/critical()
│   │   └── 使用示例
│   └── 环境变量
│
├── SDK_BEST_PRACTICES.md           # 最佳实践
│   ├── 架构设计
│   │   ├── 分离关注点
│   │   ├── 可配置化处理
│   │   └── 状态机模式
│   ├── 性能优化
│   │   ├── 轮询间隔
│   │   ├── 批量处理
│   │   ├── 缓冲区调优
│   │   ├── 日志管理
│   │   └── 性能基准
│   ├── 错误处理
│   │   ├── 分类处理
│   │   ├── 重试机制
│   │   └── 优雅降级
│   ├── 测试
│   │   ├── 单元测试
│   │   └── 集成测试
│   ├── 常见陷阱
│   │   ├── 堵塞主循环
│   │   ├── 忘记关闭资源
│   │   ├── 不正确的日志级别
│   │   ├── Schema验证性能
│   │   └── 忽视参数默认值
│   ├── 实战案例
│   │   ├── 传感器融合节点
│   │   └── 控制命令生成器
│   └── 检查清单
│
├── SDK_QUICK_REFERENCE.md          # ⚡ 速查表
│   ├── 基本结构
│   ├── SDK初始化
│   ├── 参数
│   ├── 端口
│   ├── 日志
│   ├── 常用模式
│   ├── 环境变量
│   ├── node.yaml示例
│   ├── CLI工具
│   ├── 性能建议
│   ├── 故障排查
│   └── 文档链接
│
└── STRUCTURED_LOGGING_GUIDE.md     # 日志系统详解
    ├── 概述
    ├── 架构
    ├── 节点中的使用
    ├── CLI工具
    ├── 日志文件位置
    ├── 环境变量配置
    ├── 最佳实践
    ├── 故障排除
    └── 下一步
```

## 🔍 按功能查询

### 参数和配置

- [快速入门 - 获取参数](SDK_GETTING_STARTED.md#2-获取参数)
- [API参考 - get_param()](SDK_API_REFERENCE.md#get_param)
- [最佳实践 - 模式2: 可配置化处理](SDK_BEST_PRACTICES.md#模式-2-可配置化处理)

### 端口和通信

- [快速入门 - 创建端口](SDK_GETTING_STARTED.md#3-创建端口)
- [快速入门 - 数据通信](SDK_GETTING_STARTED.md#4-数据通信)
- [API参考 - InputPort](SDK_API_REFERENCE.md#inputport)
- [API参考 - OutputPort](SDK_API_REFERENCE.md#outputport)

### 日志和调试

- [快速入门 - 日志记录](SDK_GETTING_STARTED.md#5-日志记录)
- [API参考 - StructuredLogger](SDK_API_REFERENCE.md#structuredlogger)
- [日志系统 - CLI工具](STRUCTURED_LOGGING_GUIDE.md#cli-日志工具)
- [最佳实践 - 日志级别管理](SDK_BEST_PRACTICES.md#4-日志级别管理)

### 性能和优化

- [最佳实践 - 性能优化](SDK_BEST_PRACTICES.md#性能优化)
- [快速参考 - 性能建议](SDK_QUICK_REFERENCE.md#性能建议)
- [API参考 - 环境变量](SDK_API_REFERENCE.md#环境变量)

### 错误处理

- [快速入门 - 错误处理](SDK_GETTING_STARTED.md#错误处理)
- [最佳实践 - 错误处理](SDK_BEST_PRACTICES.md#错误处理)
- [快速参考 - 故障排查](SDK_QUICK_REFERENCE.md#故障排查)

### 设计模式

- [最佳实践 - 架构设计](SDK_BEST_PRACTICES.md#架构设计)
  - 分离关注点
  - 可配置化处理
  - 状态机模式
- [最佳实践 - 实战案例](SDK_BEST_PRACTICES.md#实战案例)

## 🎓 学习路径

### 初学者（0-30分钟）

1. ⭐ [快速入门](SDK_GETTING_STARTED.md) - 理解基础概念
2. ⚡ [快速参考](SDK_QUICK_REFERENCE.md) - 快速查询API
3. 🔍 查看 `node-hub/` 下的简单节点示例

### 中级（30分钟-2小时）

1. 📘 [API参考](SDK_API_REFERENCE.md) - 掌握完整API
2. 📗 [最佳实践 - 架构设计](SDK_BEST_PRACTICES.md#架构设计) - 学习设计模式
3. 📕 [日志系统](STRUCTURED_LOGGING_GUIDE.md) - 掌握调试工具

### 高级（2小时+）

1. 📗 [最佳实践 - 完整阅读](SDK_BEST_PRACTICES.md) - 深入理解优化技巧
2. 📕 阅读 `node-hub/` 下的复杂节点源码
3. 💡 在实际项目中应用，积累经验

## ❓ 常见问题快速定位

| 问题 | 查看文档 |
|------|---------|
| 如何创建我的第一个节点？ | [快速入门](SDK_GETTING_STARTED.md) |
| 如何读写数据？ | [API参考 - InputPort/OutputPort](SDK_API_REFERENCE.md#inputport) |
| 如何记录日志？ | [API参考 - StructuredLogger](SDK_API_REFERENCE.md#structuredlogger) |
| 如何从YAML获取参数？ | [API参考 - get_param()](SDK_API_REFERENCE.md#get_param) |
| 节点太慢，如何优化？ | [最佳实践 - 性能优化](SDK_BEST_PRACTICES.md#性能优化) |
| 数据丢失了，怎么办？ | [最佳实践 - 常见陷阱](SDK_BEST_PRACTICES.md#陷阱-1-堵塞主循环) |
| 如何使用Schema验证？ | [API参考 - OutputPort](SDK_API_REFERENCE.md#初始化) |
| 如何测试我的节点？ | [最佳实践 - 测试](SDK_BEST_PRACTICES.md#测试) |
| 如何查看运行日志？ | [日志系统 - CLI工具](STRUCTURED_LOGGING_GUIDE.md#cli-日志工具) |
| 什么是Late-Joiner问题？ | [API参考 - InputPort](SDK_API_REFERENCE.md#inputport) |

## 🔗 相关资源

- **SDK源码** - `sdk/` 目录
- **示例节点** - `node-hub/` 目录（22个生产节点）
- **测试** - `tests/` 目录（单元测试、集成测试）
- **CLI工具** - `tools/cli/` 目录
- **框架文档** - `docs/` 目录

## 📝 文档约定

### 代码示例

```python
# 推荐代码（✅）
code_here()

# 不推荐代码（❌）
bad_code_here()
```

### 强调级别

- ⭐ 必读
- ⚡ 速查
- 💡 高级技巧
- ⚠️  警告/易出错
- ✅ 最佳实践

### 代码块标签

```python
# SDK初始化
with NodeFlowSDK() as sdk:
    ...
```

## 🆘 获取帮助

1. **查看文档** - 按上面的指南查找相关文档
2. **检查示例** - `node-hub/` 目录下有22个真实节点
3. **诊断工具** - 用 `nodeflow logs` 和 `nodeflow monitor` 调试
4. **搜索** - 用关键词在快速参考中搜索

---

**更新时间**: 2025-12-31
**SDK版本**: 1.0
**维护者**: NodeFlow Team
