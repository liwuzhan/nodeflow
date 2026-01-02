# 规划仿真流程诊断问题修复报告

**日期**: 2025-12-26
**参考文档**: `docs/DIAGNOSTIC_REPORT.md`
**修复版本**: v1.0

## 修复概述

根据 Gemini 2.0 Pro 诊断报告中识别的三个问题，已完成以下修复：

| 优先级 | 问题 | 状态 | 修复文件 |
|-------|-----|------|---------|
| P0 - Critical | 运动控制卡顿风险 | ✅ 已修复 | `node-hub/sim_input/run.py` |
| P1 - Major | 硬编码依赖破坏拓扑灵活性 | ✅ 已修复 | `node-hub/track_controller/run.py` |
| P2 - Minor | 启动竞态条件 | ✅ 已修复 | `node-hub/sim_output/run.py` |

---

## P0: 运动控制卡顿修复

### 问题描述
- **位置**: `node-hub/sim_input/run.py:183-193`
- **原因**: `recv_latest()` 在序列号未增加时返回 `None`，导致 sim_input 立即发送零命令停止机器人
- **影响**: 频率相同但相位不同步的节点会导致"走一步停一下"的卡顿现象

### 修复方案
实现看门狗（Watchdog）超时机制：

```python
# 添加看门狗配置（lines 67-72）
self.watchdog_timeout_sec = self.params.get('watchdog_timeout_sec', 0.5)
self.watchdog_frames = int(self.watchdog_timeout_sec * self.input_frequency)
self.no_command_counter = 0
```

**核心逻辑**:
- 只有连续 N 帧（默认 0.5 秒 = 25 帧 @ 50Hz）没有新命令时才发送零命令
- 收到新命令时立即重置计数器
- 避免因临时数据不同步导致的误停止

### 代码变更
- **文件**: `node-hub/sim_input/run.py`
- **新增参数**: `watchdog_timeout_sec` (默认 0.5 秒)
- **修改行数**: Lines 67-72 (初始化), Lines 172-209 (主循环逻辑)

---

## P1: 硬编码依赖修复

### 问题描述
- **位置**: `node-hub/track_controller/run.py:98-99`
- **原因**: 直接使用 `SharedBufferLite("rtk_filter.filtered_rtk")` 硬编码上游 buffer 名称
- **影响**:
  - 违反 NodeFlow 端口映射设计原则
  - 无法通过 YAML 重新配置拓扑
  - 如果替换上游节点（如 `rtk_filter` → `ekf_node`），需修改代码

### 修复方案
完全移除硬编码的 `SharedBufferLite` 调用，使用 SDK 端口 + 本地缓存：

**修改前**:
```python
buf_rtk = SharedBufferLite("rtk_filter.filtered_rtk", create=False)
buf_np = SharedBufferLite("waypoint_selector.next_point", create=False)

# 使用 fallback 逻辑
if not rtk:
    rtk = buf_rtk.read()
```

**修改后**:
```python
# 使用 SDK 端口（不硬编码上游 buffer 名称，保持架构灵活性）
in_rtk = sdk.create_input_port("filtered_rtk")
in_np = sdk.create_input_port("next_point")

# 本地缓存：保持最后的有效值用于持续控制
last_rtk = None
last_np = None

# 只在收到新数据时更新
if rtk:
    last_rtk = rtk
```

### 代码变更
- **文件**: `node-hub/track_controller/run.py`
- **删除**: `from sdk.shared_buffer_lite import SharedBufferLite`
- **简化**: Lines 87-118，移除 fallback 逻辑，使用本地缓存

---

## P2: 启动竞态条件修复

### 问题描述
- **位置**: `node-hub/sim_output/run.py:132-145`
- **原因**: 如果仿真器未就绪，节点使用默认地块（100x200m 矩形），导致规划浪费
- **影响**:
  1. 基于错误地块开始规划
  2. 仿真器就绪后重新规划
  3. 浪费计算资源和日志混乱

### 修复方案
在初始化时添加重试机制：

```python
def _get_field_with_retry(self, max_retries: int = 5, retry_delay: float = 0.5):
    """带重试机制获取地块信息（解决启动竞态条件）"""
    for attempt in range(max_retries):
        field_data, version = self._get_field_current()

        # 如果成功获取真实地块（版本号 > 0），直接返回
        if version > 0:
            return field_data, version

        # 重试
        if attempt < max_retries - 1:
            logger.warning(f"获取地块失败，重试 ({attempt + 1}/{max_retries})...")
            time.sleep(retry_delay)

    # 最终失败仍返回默认地块（主循环会继续尝试）
    logger.warning(f"获取地块失败 {max_retries} 次，使用默认地块")
    return self._default_field(), 0
```

**策略**:
- 启动时重试 5 次，每次间隔 0.5 秒
- 总计 2.5 秒的等待窗口
- 如果仍失败，使用默认地块但继续在主循环中检测版本更新

### 代码变更
- **文件**: `node-hub/sim_output/run.py`
- **新增方法**: `_get_field_with_retry()` (Lines 132-157)
- **调用修改**: Line 112，使用 `_get_field_with_retry()` 替代直接调用

---

## 测试验证

### 单元测试
```bash
python3 -m pytest tests/ -v
```

**结果**: 118 通过 / 15 失败
- ✅ 所有核心功能测试通过
- ❌ 失败测试均为已知的基础设施问题：
  - MCP 测试需要 pytest-asyncio
  - E2E 测试需要运行中的仿真器

### 语法检查
```bash
python3 -m py_compile node-hub/sim_input/run.py \
                      node-hub/track_controller/run.py \
                      node-hub/sim_output/run.py
```
**结果**: ✅ 全部通过

### 修改影响范围
- ✅ 向后兼容：所有参数均有默认值
- ✅ 无破坏性变更：只删除了内部硬编码依赖
- ✅ 架构改进：恢复端口映射的灵活性

---

## 验证结果 (Gemini 2.0 Pro)

### 1. sim_input (P0)
- **检查项**: 看门狗逻辑实现
- **结果**: ✅ 已实现
  - `__init__` 中初始化了 `watchdog_timeout_sec` (Line 69) 和 `no_command_counter` (Line 71)。
  - `run` 循环中实现了计数器递增 (Line 196) 和超时重置 (Line 199-207)。
  - 接收到新命令时重置计数器 (Line 172, 188)。

### 2. track_controller (P1)
- **检查项**: 移除硬编码依赖
- **结果**: ✅ 已实现
  - 移除了 `SharedBufferLite` 的直接实例化。
  - 使用 `sdk.create_input_port("filtered_rtk")` (Line 96) 和 `sdk.create_input_port("next_point")` (Line 97)。
  - 实现了本地缓存 `last_rtk` / `last_np` (Line 101-102) 并在循环中更新 (Line 110-113)。

### 3. sim_output (P2)
- **检查项**: 启动重试机制
- **结果**: ✅ 已实现
  - 新增 `_get_field_with_retry` 方法 (Line 132)。
  - `__init__` 中调用了该方法替代直接获取 (Line 112)。
  - 实现了最大重试次数和延迟 (Line 143-153)。

---

## 结论
所有修复均已正确实施，代码逻辑符合诊断报告中的建议。

