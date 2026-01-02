# 车辆停止问题诊断报告（更新版）

**日期**: 2025-12-31
**最后更新**: 03:58

---

## 1. 问题现象

- 车辆在仿真中运行一段时间后停止不动（或看起来停止）
- 可视化图像显示车辆位置长时间不更新
- 实际上车辆一直在移动，但是在错误的方向上

## 2. 诊断过程

### 2.1 初步排查

使用 CLI 监控工具检查数据流：

```bash
python3 -m tools.cli.core.cli buffer list
python3 -m tools.cli.core.cli buffer inspect coord_transform.pose_enu
python3 -m tools.cli.core.cli buffer inspect waypoint_selector.next_point
```

**发现**：所有 buffer 序列号正常增长（数据流畅通）

### 2.2 详细检查各组件状态

| 组件 | 状态 | 数据 |
|------|------|------|
| coord_transform.pose_enu | ✅ 正常 | x=-13.96, y=-21.24, theta=1.57 |
| waypoint_selector.next_point | ⚠️ 异常 | x=-13.88, y=42.57, **consumed=0, index=0** |
| track_controller.velocity_cmd | ✅ 正常 | v=1.0 m/s, w=0.0005 rad/s |
| 仿真器内部状态 | ✅ 正常 | vx=0.99 m/s, 位置持续更新 |

### 2.3 根本原因定位

**关键发现：**

1. **路径消费完全失效**：
   - waypoint_selector 的 `consumed=0`（一个点都没消费）
   - 一直追踪第0个点作为目标

2. **车辆位置与路径起点严重不匹配**：
   - 车辆当前位置：(-13.96, -21.24)
   - 路径第0点：(-13.88, 42.57)
   - **距离：63.8米！**

3. **车辆实际上在路径中间位置**：
   ```
   路径总点数: 6549
   距离车辆最近的点: 第 4581 点，仅 1.0m
   但 waypoint_selector 仍然追踪第 0 点（63.8m之外）
   ```

4. **初始消费机制失效原因**：
   ```yaml
   initial_check_points: 50       # ❌ 只检查前50个点
   initial_consume_distance: 2.0  # 距离<2m才消费
   ```

   - 前50个点距车辆都在50-63米之外
   - 初始消费找不到距离<2m的点，返回0
   - 后续持续消费也只检查前10个未消费点，仍然无法触发

---

## 3. 根本原因总结

**waypoint_selector 的初始消费机制设计缺陷**：

1. **假设车辆总是从路径起点附近启动**
2. **只检查前 N 个点**（默认50个）
3. **当车辆从路径中间位置启动时，无法跳跃到正确的起始点**

这导致：
- 车辆一直追踪第0个点（实际上在另一端63米之外）
- 车辆持续移动但永远无法靠近目标点（因为路径是往复式的）
- 看起来像是"停止不动"（实际上是在错误方向上移动）

---

## 4. 修复方案

### 4.1 临时修复（已应用）

修改 `examples/planning_simulation.yaml`：

```yaml
initial_check_points: 10000    # 从 50 增加到 10000
initial_consume_distance: 5.0  # 从 2.0 增加到 5.0
```

**原理**：
- 扩大初始检查范围到整个路径（10000 > 6549）
- 找到距离车辆最近的点（第4581点，1.0m）
- 自动消费前4581个点，从正确的位置开始

### 4.2 长期改进建议

**修改 `waypoint_selector/atom.py` 的 `_initial_consume` 方法**：

```python
def _initial_consume(self, vx: float, vy: float) -> int:
    """
    改进版：扫描整个路径，找到距离车辆最近的点
    """
    path = self.state.path
    cfg = self.config

    # 扫描整个路径（而不是只检查前N个）
    min_dist = float('inf')
    closest_idx = -1

    for i, (px, py) in enumerate(path):
        dist = self.euclidean_distance(vx, vy, px, py)
        if dist < min_dist:
            min_dist = dist
            closest_idx = i

    # 如果最近的点距离合理（<10m），则消费它之前的所有点
    if closest_idx >= 0 and min_dist < 10.0:
        return closest_idx

    return 0
```

---

## 5. 验证步骤

1. **重启 runtime** 应用新配置：
   ```bash
   python3 -m runtime.main examples/planning_simulation.yaml
   ```

2. **监控 waypoint_selector 状态**：
   ```bash
   python3 -m tools.cli.core.cli buffer inspect waypoint_selector.next_point
   ```

   期望看到：
   ```json
   {
     "consumed": 4581,  // 不再是 0
     "index": 4582,     // 从最近点开始
     "mode": "tracking" // 或 "approach"
   }
   ```

3. **监控车辆轨迹**：
   - 查看可视化图像
   - 确认车辆沿规划路径移动

---

## 6. 其他发现

### 6.1 RTK rate limiting（已排除）

- RTK 频率限制导致 60% 请求返回 null
- 但剩余 40% 仍足以提供位置更新（约 8Hz）
- 已通过调整频率配置解决：
  ```yaml
  simulator: rtk.frequency: 50.0  # 从 20Hz 提高
  sim_output: output_frequency: 20.0  # 从 50Hz 降低
  ```

### 6.2 持续消费机制（已添加安全限制）

- 只检查前10个未消费点
- 必须连续消费（不能跳跃）
- 避免误消费序列上很远的点

---

## 7. 经验总结

1. **监控工具的重要性**：
   - `buffer list` 查看数据流是否畅通
   - `buffer inspect` 检查数据内容
   - 结合仿真器状态查询（ZMQ）确认真实状态

2. **初始化机制需要考虑所有场景**：
   - 不能假设车辆总是从固定位置启动
   - 仿真器可能随机放置车辆
   - 需要全路径扫描找到最近点

3. **算法设计的健壮性**：
   - 配置参数应该有合理的默认值
   - 边界情况需要充分考虑
   - 调试日志应该足够详细

---

## 附录：监控命令速查

```bash
# 查看所有缓冲区状态
python3 -m tools.cli.core.cli buffer list

# 检查关键数据
python3 -m tools.cli.core.cli buffer inspect coord_transform.pose_enu
python3 -m tools.cli.core.cli buffer inspect waypoint_selector.next_point
python3 -m tools.cli.core.cli buffer inspect track_controller.velocity_cmd

# 查询仿真器状态
python3 -c "
import zmq, json
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect('tcp://localhost:5555')
sock.setsockopt(zmq.RCVTIMEO, 2000)
sock.send_json({'type': 'get_state'})
print(json.dumps(sock.recv_json(), indent=2))
sock.close()
ctx.term()
"

# 查看节点日志
tail -f /tmp/nodeflow/logs/waypoint_selector.log
tail -f /tmp/nodeflow/logs/sim_output.stderr.log
```
