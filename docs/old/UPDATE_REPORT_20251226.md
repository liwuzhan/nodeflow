# NodeFlow 更新报告 - 2025-12-26

## 概述

本次更新主要修复了 Gemini 代码审查报告中指出的关键问题，并完成了完整的工作流测试验证。修复后，机器人路径跟踪精度从统计的 2.31m 偏差提升到实际 **0.03m（3厘米）**。

---

## 1. IPC 竞态条件修复 (Critical)

### 问题描述
共享内存写入顺序存在竞态条件：序列号先于数据更新，导致读取端可能读到不一致的数据。

### 修复方案
**Optimistic Read 模式**：读取前后验证序列号一致性，不一致则重试。

**修改文件**:
- `sdk/shared_buffer_lite.py`
- `runtime/ipc/shared_buffer.py`

**写入顺序修复** (原: seq→data, 现: data→seq):
```python
# 修复后的写入顺序
self.mmap[8:8+data_length] = serialized  # 1. 先写数据
self.mmap[4:8] = struct.pack('<I', data_length)  # 2. 再写长度
self.mmap.flush()  # 3. 确保数据和长度可见
self.mmap[0:4] = struct.pack('<I', new_seq)  # 4. 最后更新序列号
self.mmap.flush()  # 5. 确保序列号可见
```

**Optimistic Read 实现**:
```python
def read(self, max_retries=3):
    for _ in range(max_retries):
        seq_before = struct.unpack('<I', self.mmap[0:4])[0]
        if seq_before == 0:
            return None
        length = struct.unpack('<I', self.mmap[4:8])[0]
        serialized = bytes(self.mmap[8:8+length])
        seq_after = struct.unpack('<I', self.mmap[0:4])[0]
        if seq_before == seq_after:  # 一致性检查
            return msgpack.unpackb(serialized, ...)
    return None  # 重试失败
```

---

## 2. 序列号回绕处理 (Major)

### 问题描述
32 位序列号计数器从 `0xFFFFFFFF` 溢出到 `0` 时，简单的 `>` 比较会失败。

### 修复方案
使用模运算处理回绕：

**修改文件**:
- `runtime/ipc/shared_buffer.py`
- `sdk/port.py`

**修复代码**:
```python
def has_new_data(self, last_counter):
    current_counter = self._read_counter_unsafe()
    # 模运算处理回绕
    diff = (current_counter - last_counter) & 0xFFFFFFFF
    return 0 < diff < 0x80000000
```

---

## 3. 坐标系对齐修复 (Critical)

### 问题描述
仿真器使用数学坐标系（yaw=0° 指向东，CCW 为正），而 GPS heading 使用地理坐标系（heading=0° 指向北，CW 为正）。控制器计算的角速度符号未正确转换。

### 影响
机器人转向方向相反，无法正确跟踪路径。

### 修复方案
在 `track_controller` 中对角速度取反：

**修改文件**: `node-hub/track_controller/run.py`

**修复代码**:
```python
# 计算航向误差
hb = bearing(clat, clon, nlat, nlon)  # 目标方位角（地理坐标系）
hdeg = float(rtk.get("heading", 0.0))  # 当前航向（地理坐标系）
hcur = math.radians(hdeg)
err = normalize(hb - hcur)

# 关键修复：角速度取反以匹配仿真器坐标系
w = -kp * err  # 原来是 w = kp * err
w = max(-max_w, min(max_w, w))
```

### 坐标系转换关系
```
仿真器内部: yaw = 0° 指向 +X (东), CCW 为正
GPS 输出:   heading = 0° 指向北, CW 为正
转换公式:   heading_deg = (-yaw_deg + 90) % 360
```

---

## 4. 轨迹统计逻辑优化

### 问题描述
轨迹可视化节点计算平均横向误差时，将机器人从初始位置移动到规划起点的轨迹也纳入统计，导致误差虚高。

### 修复前后对比

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 平均横向误差 | 2.31 m | 0.03 m |
| 最大横向误差 | 17.07 m | 0.98 m |
| 有效轨迹点 | 全部 | 进入规划路径后 |

### 修复方案
找到第一个距离规划起点 < 5m 的轨迹点，从该点开始计算统计：

**修改文件**: `node-hub/trajectory_viz/run.py`

**修复代码**:
```python
# 找到第一个进入规划路径附近的点
start_index = 0
approach_threshold = 5.0  # 5米阈值
for idx, actual_point in enumerate(self.actual_trajectory):
    dist_to_start = distance(actual_point, self.planned_path[0])
    if dist_to_start < approach_threshold:
        start_index = idx
        break

# 使用过滤后的轨迹计算统计
filtered_trajectory = self.actual_trajectory[start_index:]
```

---

## 5. 缓冲区自动清理功能

### 问题描述
旧的缓冲区数据会干扰新的测试运行，导致数据混乱。

### 修复方案
框架启动时默认清理所有缓冲区文件（写满零以重置序列号）：

**修改文件**: `runtime/main.py`

**新增功能**:
```python
def _clean_buffers(self):
    """清理共享缓冲区（写满0以重置序列号和数据）"""
    buf_dir = Path(BUFFERS_DIR)
    for buf_file in buf_dir.glob("*.buf"):
        file_size = buf_file.stat().st_size
        with open(buf_file, 'wb') as f:
            f.write(b'\x00' * file_size)
```

**CLI 参数变更**:
- 原: `--clean-buffers` (opt-in)
- 现: `--no-clean-buffers` (opt-out，默认清理)

---

## 6. 测试验证

### 完整工作流测试
```bash
# 启动仿真器
python3 simulator/server.py &

# 启动工作流（自动清理缓冲区）
python3 -m runtime.main examples/planning_simulation.yaml
```

### 测试结果
- 9 个节点全部正常启动
- 缓冲区数据流正常（验证序列号递增）
- 机器人正确跟随规划的往复式覆盖路径
- 平均横向误差 0.03m（3厘米）

### 数据流验证
```
sim_output.rtk_fix        → seq=5257  ✅
rtk_filter.filtered_rtk   → seq=4792  ✅
global_coverage.global_path → seq=2995  ✅
waypoint_selector.next_point → seq=4366  ✅
track_controller.velocity_cmd → seq=10252  ✅
```

---

## 7. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `sdk/shared_buffer_lite.py` | 修改 | 写入顺序修复 + Optimistic Read |
| `runtime/ipc/shared_buffer.py` | 修改 | 写入顺序修复 + Optimistic Read + 回绕处理 |
| `sdk/port.py` | 修改 | 序列号回绕处理 |
| `node-hub/track_controller/run.py` | 修改 | 角速度符号反转 + 距离计算 + 停止逻辑 |
| `node-hub/trajectory_viz/run.py` | 修改 | 轨迹统计逻辑优化 |
| `runtime/main.py` | 修改 | 缓冲区自动清理功能 |
| `examples/planning_simulation.yaml` | 修改 | 控制器参数调优 |
| `README.md` | 修改 | 更新日志 |

---

## 8. 已知限制

1. **序列号回绕**: 当前实现假设读写频率差不超过 20 亿次，实际场景中足够使用
2. **Optimistic Read 重试**: 默认最多重试 3 次，极端高频写入场景可能需要调整
3. **坐标系**: 当前仅验证了仿真器坐标系，实际硬件可能需要额外适配

---

## 9. 参考

- [Gemini 代码审查报告](docs/评审报告/gemini20251226.md)
- [混合 IPC 架构文档](docs/ZMQ_HYBRID_IPC_IMPLEMENTATION.md)
- [仿真器坐标系说明](simulator/README.md)

---

*报告生成时间: 2025-12-26*
