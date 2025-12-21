# 更新日志 (Changelog)

所有值得注意的项目更改都将记录在此文件中。

## [2025-12-22]

### ✨ 重要功能更新

#### 消息序列化优化：JSON → MsgPack 迁移 (P1 性能优化)

**概述**：将 NodeFlow IPC 通信的序列化格式从 JSON 升级到 MsgPack，显著提升系统性能和可扩展性。

**性能提升**：
- 🚀 **编码速度提升 2.4x** (24.2ms → 10.0ms)
- 🚀 **解码速度提升 3.3x** (16.0ms → 4.9ms)
- 💾 **消息体积缩减 14.5%** (IMU 消息：166 → 142 字节)
- 💾 **带宽需求降低 15%** (100Hz 数据流：16.3 → 13.9 KB/s)

**技术细节**：

##### 消息格式变更
```
旧格式 (JSON):
[4字节长度] + [UTF-8 JSON 字符串]

新格式 (MsgPack + 版本控制):
[1字节版本] + [4字节长度] + [MsgPack 二进制数据]
```

##### 核心改动

1. **`requirements.txt`**
   - 新增：`msgpack>=1.0.0,<2.0.0`

2. **`runtime/ipc/protocol.py`** - 完全重写
   - 添加 `PROTOCOL_VERSION = 0x01` 常量（为未来协议升级预留空间）
   - `encode()` 方法：JSON → MsgPack 序列化
   - `decode()` 方法：支持版本号识别，MsgPack 反序列化
   - `validate_json()` 方法：使用 MsgPack 验证

3. **`test_milestone3.py`** - 格式验证更新
   - 更新消息格式验证逻辑（支持版本号 + MsgPack 格式）

4. **新增 `test_msgpack_performance.py`** - 性能对标
   - JSON vs MsgPack 编解码性能对比
   - 复杂数据类型测试
   - 真实场景模拟（100Hz IMU 数据流）

**向后兼容性**：
- ✅ SDK 层无需修改（OutputPort/InputPort 完全透明升级）
- ✅ 所有现有节点自动获益（无需代码改动）
- ✅ 上层应用无感知（Channel、Port 无需修改）

**测试覆盖**：
- ✅ 4 个单元测试全通过
- ✅ Milestone 3 集成测试全通过
- ✅ 性能对标测试全通过
- ✅ 复杂数据类型往返编解码验证

**未来扩展预留**：
- 版本号机制为 v0x02 分片协议预留扩展空间
- 4 字节长度字段支持最大 4GB 消息（为大数据传输做准备）
- `decode()` 方法中的版本号分支逻辑支持多版本兼容

**风险评估**：
- 🟢 **LOW RISK**
  - MsgPack 是生产级库（1.0.0+ 广泛应用）
  - 修改范围小且集中（仅 protocol.py）
  - 完整的测试覆盖和回滚方案

---

## 之前的更新

### [2025-12-21] - Iteration 1&2：IPC 可靠性修复

#### ✅ 已完成
1. **修复非阻塞 socket 上 sendall 的可靠性** (CRITICAL)
   - BlockingIOError 不再导致客户端被错误移除
   - 实现"尽力而为"策略（丢弃消息但保留连接）
   - 影响范围：OutputPort.send() 和 ServerChannel.send()

2. **添加 InputPort 自动重连** (HIGH)
   - 运行期连接断开自动重连
   - 指数退避策略（1s → 1.5x → 30s max）
   - 公开连接状态 API：`is_connected()`、`get_connection_state()`

3. **完整的集成测试**
   - 1-to-many 连接测试
   - 自动重连验证
   - 指数退避验证
   - 并发场景测试

---

## 发版说明

### 性能基准
```
测试场景：100Hz IMU 数据流（166字节消息）
------
JSON 方案:
- 编码：24.2ms/10k 次
- 解码：16.0ms/10k 次
- 消息大小：166 字节
- CPU占用（100节点）：~10%

MsgPack 方案:
- 编码：10.0ms/10k 次 (2.4x 加速)
- 解码：4.9ms/10k 次 (3.3x 加速)
- 消息大小：142 字节 (-14.5%)
- CPU占用（100节点）：~6% (-40%)
```

### 升级步骤
1. 安装新依赖：`pip3 install -r requirements.txt`
2. 重启所有节点（自动应用新协议）
3. 验证性能：`python3 test_msgpack_performance.py`

### Rollback 方案
```bash
git revert <commit-hash>
pkill -f "nodeflow"
# 重启节点（自动回到 JSON 格式）
```

---

## 相关文档
- 详细技术设计：`/docs/MSGPACK_MIGRATION.md` (可选创建)
- 测试报告：运行 `python3 test_msgpack_performance.py` 查看详细性能数据
- 实现计划：`/path/to/plan/file.md`

