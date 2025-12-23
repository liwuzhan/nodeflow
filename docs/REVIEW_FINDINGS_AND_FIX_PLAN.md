# 通讯方式评审与修复计划（2025-12-24）

## 概述

基于 GPT 评审报告（`docs/评审报告/gpt评审20251224_通讯方式.md`），针对 NodeFlow Hybrid IPC 架构的三个主要问题制定修复计划。

---

## 问题总结

| 等级 | 问题 | 状态 | 优先级 |
|------|------|------|--------|
| Major 1 | pyzmq 依赖缺失 | ✅ 已修复 | P0 |
| Major 2 | Late-Joiner 语义未完全实现 | 📋 待规划 | P1 |
| Major 3 | JSON 序列化与大数据定位不符 | 📋 待规划 | P2 |
| Minor 1 | 两套 IPC 栈共存 | 📋 待规划 | P2 |

---

## ✅ P0: pyzmq 依赖缺失 - 已修复

### 问题描述
- SDK (`sdk/port.py:11`) 直接导入 `zmq`
- `requirements.txt` 未声明 `pyzmq` 依赖
- 干净环境安装后运行节点会报 `ImportError: No module named 'zmq'`

### 修复方案
在 `requirements.txt` 中添加 `pyzmq>=24.0.0`

### 修复状态
✅ **已完成**
```diff
+ pyzmq>=24.0.0
```

### 验证步骤
```bash
# 在干净虚拟环境中验证
python3 -m venv test_env
source test_env/bin/activate
pip install -r requirements.txt

# 验证 zmq 可导入
python3 -c "import zmq; print(f'ZMQ version: {zmq.zmq_version()}')"

# 运行测试
pytest tests/integration/test_buffer_config.py -v
```

---

## 📋 P1: Late-Joiner 语义完整性 - 待规划

### 问题描述

**文档承诺**:
- `docs/SESSION_SUMMARY_20251224.md`: "无数据丢失，不受节点启动顺序影响"
- `docs/ZMQ_HYBRID_IPC_IMPLEMENTATION.md`: SharedBuffer 作为"持久化数据存储"

**实现现状**:
- InputPort 首次连接时只同步序列号（`sdk/port.py:289-292`）
- 不返回历史值，下游节点可能读不到上游已发送的数据

**典型场景**:
```
时间线：
1. 上游节点启动，发送数据 seq=1，数据写入 buffer
2. 发送 ZMQ 通知，调用者 recv_latest() → 读到 data
3. 下游节点启动，连接 InputPort，last_sequence 同步为 1
4. 下游调用 recv_latest()，检查 current_seq == last_sequence，跳过读取 → 丢数据 ❌
```

### 建议的修复方案

#### Option A: 首次连接读历史值（推荐）

修改 `sdk/port.py` 中 InputPort 的首次连接逻辑：

```python
def _setup(self):
    """首次连接时从缓冲区读取历史值"""

    # ... 现有代码 ...

    # 新增：首次连接读历史
    try:
        history_data = self.buffer.read()
        if history_data and self.last_sequence < self.buffer.get_sequence():
            self.last_sequence = self.buffer.get_sequence()
            self._cached_data = history_data
            logger.info(f"Late joiner reading history: seq={self.last_sequence}")
    except Exception as e:
        logger.warning(f"Failed to read history: {e}")
```

#### Option B: 增加"首次同步数据"消息（备选）

上游节点对新连接的 InputPort 主动发送一条"历史值"消息，确保下游能收到最新值。

### 验收标准

1. **单元测试**：`tests/integration/test_late_joiner.py`
   - 测试：上游发送一次，下游晚启动，读取历史值
   - 预期：下游首次 `recv_latest()` 成功读到上游数据

2. **集成测试**：使用 `examples/` 中的场景验证
   - 4层启动拓扑，验证所有下游都能读到上游数据

3. **文档更新**：
   - 在 `README.md` 中明确"Late Joiner 可读性保证"
   - 在 `docs/BUFFER_CONFIG_IMPLEMENTATION.md` 中补充说明

### 修复优先级
🔴 **高** - 这是"混合架构"的核心承诺，不完成会导致用户遭遇数据丢失

---

## 📋 P2: 序列化策略对齐 - 待规划

### 问题描述

**现状**:
- SharedBufferLite 使用 JSON 序列化（`sdk/shared_buffer_lite.py:12,65`）
- JSON 对二进制/大数组支持弱

**文档定位**:
- README：激光雷达、4K 摄像头支持（5-50MB）
- SESSION_SUMMARY：支持"大数据量传感器"

**矛盾**:
```python
# 当前实现
data = json.dumps(payload)  # ❌ numpy.ndarray 无法序列化
json.loads(buffer_data)     # ❌ 性能不佳，体积偏大
```

### 建议的修复方案

#### 方案：统一使用 MsgPack

代码库已存在 MsgPack 实现（`runtime/ipc/protocol.py`、`runtime/ipc/shared_buffer.py`），可复用。

**修改 `sdk/shared_buffer_lite.py`**:

```python
import msgpack  # 替代 json

class SharedBufferLite:
    def write(self, data: Any) -> bool:
        """使用 MsgPack 序列化"""
        try:
            serialized = msgpack.packb(
                data,
                default=self._encode_numpy,  # 支持 numpy array
                use_bin_type=True
            )
            # ... 写入 buffer ...
        except Exception as e:
            logger.error(f"Failed to serialize: {e}")
            return False

    @staticmethod
    def _encode_numpy(obj):
        """支持 numpy 数组"""
        if isinstance(obj, np.ndarray):
            return {'__ndarray__': True, 'data': obj.tobytes(), 'dtype': str(obj.dtype), 'shape': obj.shape}
        raise TypeError(f"Unknown type: {type(obj)}")
```

**验收标准**:

1. 单元测试：`tests/integration/test_msgpack_buffer.py`
   - 支持 dict, list, bytes, numpy.ndarray, nested structures

2. 性能测试
   - JSON vs MsgPack 序列化速度、体积对比
   - 激光雷达点云数据（100K-1M points）的序列化测试

3. 文档更新
   - 在 README 中明确"支持的数据类型"
   - 在 `docs/BUFFER_CONFIG_IMPLEMENTATION.md` 中补充"序列化格式"

### 修复优先级
🟡 **中** - 目前使用 JSON 也能工作，但为了支持大数据场景应该优化

---

## 📋 P2: 两套 IPC 栈梳理 - 待规划

### 问题描述

代码库同时存在：

1. **新栈（主路径）**
   - `sdk/port.py`：ZeroMQ + SharedBufferLite
   - `runtime/orchestrator/env_builder.py`：ZMQ 地址注入
   - `runtime/orchestrator/startup_coordinator.py`：拓扑启动

2. **旧栈（遗留）**
   - `runtime/ipc/channel.py`：Unix Socket
   - `runtime/ipc/protocol.py`：MsgPack + length prefix
   - `runtime/ipc/shared_buffer.py`：MsgPack mmap buffer
   - `sdk/latest_value_reader.py`：旧读取器
   - `runtime/ipc/socket_manager.py`：Socket 管理

### 问题影响

- 文档、测试、示例可能混用两套实现
- 新成员开发时被双实现误导
- 维护成本上升

### 建议的修复方案

#### 方案：清晰标注与逐步淘汰

1. **文档标注**
   - 在 `runtime/ipc/` 目录下添加 `README_LEGACY.md`，明确标注"已弃用，仅保留向后兼容"
   - 在 `sdk/latest_value_reader.py` 顶部添加 `Deprecated` 注释

2. **代码标注**
   ```python
   # 在 runtime/ipc/*.py 顶部
   """
   ⚠️ DEPRECATED: This module is no longer used in the main IPC path.

   Current stack: sdk/port.py (ZeroMQ + SharedBufferLite) + runtime/orchestrator/env_builder.py

   This module is kept for backward compatibility only.
   See docs/BUFFER_CONFIG_IMPLEMENTATION.md for current architecture.
   """
   ```

3. **清理 runtime/main.py**
   - 移除 `SocketManager` 初始化（当前被注释为"保留但未使用"）
   - 在日志中明确说明"Using ZeroMQ + SharedBuffer IPC"

### 修复优先级
🟡 **中** - 不影响功能，但提升可维护性

---

## 📅 修复时间表

| 优先级 | 问题 | 修复内容 | 预期工期 | 状态 |
|--------|------|--------|---------|------|
| P0 | pyzmq 缺失 | 更新 requirements.txt | 5min | ✅ 完成 |
| P1 | Late-Joiner | 新增历史读取、测试、文档 | 2h | 📋 待做 |
| P2 | JSON→MsgPack | 序列化重写、性能测试 | 3h | 📋 待做 |
| P2 | 栈清理 | 标注、文档、清理 | 1h | 📋 待做 |

---

## 修复检查清单

### P0 完成度
- [x] 添加 `pyzmq>=24.0.0` 到 requirements.txt
- [x] 验证导入可用
- [ ] 更新 README 安装说明（可选增强）

### P1 待启动
- [ ] 实现 InputPort 首次读历史值逻辑
- [ ] 编写 `test_late_joiner.py`
- [ ] 更新 README 和文档
- [ ] 运行集成测试验证

### P2 待启动
- [ ] 替换 JSON 为 MsgPack 序列化
- [ ] 实现 numpy.ndarray 支持
- [ ] 编写性能测试
- [ ] 更新数据类型文档
- [ ] 在 runtime/ipc/ 添加 LEGACY 标注
- [ ] 清理 runtime/main.py

---

## 相关文档

- 原始评审报告：`docs/评审报告/gpt评审20251224_通讯方式.md`
- 当前实现文档：`docs/BUFFER_CONFIG_IMPLEMENTATION.md`
- 架构文档：`docs/ZMQ_HYBRID_IPC_IMPLEMENTATION.md`
- README：已更新为 Hybrid 架构说明

---

## 评审报告建议总结

| 建议 | 类型 | 影响度 | 状态 |
|------|------|--------|------|
| 声明 pyzmq 依赖 | P0 | 阻断 | ✅ 已处理 |
| 完整 Late-Joiner 实现 | P1 | 功能正确性 | 📋 计划中 |
| 统一序列化为 MsgPack | P2 | 性能与可扩展 | 📋 计划中 |
| 标注过期 IPC 栈 | P2 | 代码清晰度 | 📋 计划中 |

---

*本文档由评审指导生成，记录修复计划与验收标准。*
