# Socket传输问题修复方案

**时间**: 2025-12-23 16:30
**优先级**: P0 Critical

---

## 问题分析

### 1. global_coverage: 一次性发送导致数据丢失

**当前实现** (错误):
```python
# global_coverage/run.py 第79-86行
path_points = planner.plan(parcel, vehicle)
result = {'task_id': task_id, 'path': path_points, 'status': 'success'}
output_port.send(result)  # ← 只发送一次!

# 之后就进入等待新任务的循环
while True:
    task_data = input_port.recv_latest()
    # 如果task_id相同，跳过
```

**问题**:
- 规划完成后只发送一次路径
- 如果velocity_controller还未连接(Layer 2在60秒后启动)
- 路径数据会被丢弃，velocity_controller永远收不到

---

### 2. velocity_controller: 路径索引管理问题

**当前实现** (有缺陷):
```python
# velocity_controller/run.py

class PurePursuitController:
    def __init__(self):
        self.path = []
        self.current_path_index = 0  # 路径索引

    def set_path(self, path: list):
        """设置路径"""
        self.path = path
        self.current_path_index = 0  # ← 每次都重置为0!

    def find_lookahead_point(self, current_lat, current_lon):
        """查找前瞻点"""
        for i in range(self.current_path_index, len(self.path)):
            # 找到距离>前瞻距离的点
            if d >= self.lookahead_distance:
                return lat, lon, d
        # ← 注意: 没有更新self.current_path_index!

# 主循环
while True:
    global_path = global_path_port.recv_latest()
    if global_path and 'path' in global_path:
        controller.set_path(global_path['path'])  # ← 每次都重置索引!
```

**问题1**: 路径索引从不更新
- `current_path_index`永远是0
- 每次都从起点开始查找前瞻点
- 效率低，且可能导致异常行为

**问题2**: 重复接收路径会重置进度
- 如果持续接收相同的路径(修复后的global_coverage)
- 每次`set_path()`都会重置`current_path_index = 0`
- 机器人会"回到起点"，无法前进

---

## 修复方案

### 方案A: 最小修改 (推荐 - 2分钟修复)

#### 1. 修复global_coverage - 持续发送路径

```python
# node-hub/global_coverage/run.py
# 在第86行 output_port.send(result) 之后添加循环

# 发送结果
result = {
    'task_id': task_id,
    'timestamp': time.time(),
    'path': path_points,
    'status': 'success' if path_points else 'failed',
    'metadata': {
        'planning_duration': duration,
        'num_points': len(path_points)
    }
}

# 持续发送路径，保证下游随时可接收
sdk.logger.info(f"开始持续发送路径 (task_id={task_id})")
last_task_id = task_id  # 更新已处理的task_id

while True:
    # 持续发送当前路径
    output_port.send(result)

    # 检查是否有新任务
    new_task = input_port.recv_latest()
    if new_task and isinstance(new_task, dict):
        new_task_id = new_task.get('id')
        if new_task_id and new_task_id != last_task_id:
            sdk.logger.info(f"收到新任务: {new_task_id}，停止发送旧路径")
            break  # 退出循环，重新规划

    time.sleep(0.1)  # 10Hz发送频率
```

**优点**:
- 简单直接，只需修改global_coverage
- 保证下游随时可以接收路径
- 收到新任务时自动停止旧路径

**缺点**:
- velocity_controller仍然会重复接收相同路径

#### 2. 修复velocity_controller - 避免重复设置路径

```python
# node-hub/velocity_controller/run.py
# 在第296行添加路径版本号追踪

class PurePursuitController:
    def __init__(self, ...):
        # 现有代码...
        self.path = []
        self.current_path_index = 0
        self.current_task_id = None  # ← 添加: 路径版本追踪

    def set_path(self, path: list, task_id: str = None):
        """设置路径 (带版本号检测)"""
        # 如果是相同的路径，不重置索引
        if task_id and task_id == self.current_task_id:
            return  # 跳过重复设置

        self.path = path
        self.current_path_index = 0
        self.current_task_id = task_id
        logger.info(f"路径已更新: {len(path)}个点 (task_id={task_id})")

# 主循环中修改 (第348-349行)
if global_path and 'path' in global_path:
    task_id = global_path.get('task_id', None)
    controller.set_path(global_path['path'], task_id)
```

**优点**:
- 避免重复接收导致索引重置
- 只在真正新路径时才重置

**缺点**:
- 仍然没有更新路径索引

---

### 方案B: 完整修复 (推荐 - 10分钟修复)

在方案A的基础上，增加路径点通过检测:

```python
# node-hub/velocity_controller/run.py

def find_lookahead_point(self, current_lat: float, current_lon: float):
    """查找前瞻点 (带路径点通过检测)"""
    if not self.path:
        return None, None, None

    # 更新路径索引: 跳过已经通过的点
    while self.current_path_index < len(self.path):
        lon, lat = self.path[self.current_path_index]
        d = haversine_distance(current_lat, current_lon, lat, lon)

        # 如果当前点已经很近(<goal_tolerance)，认为已通过
        if d < self.goal_tolerance:
            self.current_path_index += 1
            logger.debug(f"已通过路径点 #{self.current_path_index}")
        else:
            break  # 找到第一个未通过的点

    # 如果所有点都已通过
    if self.current_path_index >= len(self.path):
        logger.info("已完成整条路径!")
        return None, None, None

    # 从当前索引开始找前瞻点
    for i in range(self.current_path_index, len(self.path)):
        lon, lat = self.path[i]
        d = haversine_distance(current_lat, current_lon, lat, lon)
        if d >= self.lookahead_distance:
            return lat, lon, d

    # 如果没找到，返回终点
    lon, lat = self.path[-1]
    d = haversine_distance(current_lat, current_lon, lat, lon)
    return lat, lon, d
```

**优点**:
- 自动跳过已通过的点
- 正确追踪路径进度
- 到达终点后停止

---

## 实施步骤

### 步骤1: 修复global_coverage (2分钟)

```bash
# 编辑文件
nano /Users/wuzhanli/Desktop/node/node-hub/global_coverage/run.py

# 在第86行后添加持续发送循环 (见方案A)
```

### 步骤2: 修复velocity_controller (5分钟)

```bash
# 编辑文件
nano /Users/wuzhanli/Desktop/node/node-hub/velocity_controller/run.py

# 1. 添加路径版本号追踪 (第113-115行)
# 2. 修改set_path()方法 (第117-122行)
# 3. 添加路径点通过检测 (第128-165行)
# 4. 修改主循环 (第348-350行)
```

### 步骤3: 验证修复 (10分钟)

```bash
# 清理旧日志
rm -rf /tmp/nodeflow_logs/

# 启动仿真器
python3 simulator/server.py &

# 运行完整闭环
python3 -m runtime.main examples/planning_minimal.yaml

# 观察日志
tail -f /tmp/nodeflow_logs/velocity_controller.stderr.log

# 预期输出:
# "路径已更新: 74个点 (task_id=task_xxx)"
# "已通过路径点 #1"
# "已通过路径点 #2"
# ...
# "控制: v=1.000 m/s, ω=0.125 rad/s"
```

---

## 预期结果

修复后的系统行为:

1. **sim_output**: 持续发送RTK (50Hz) 和 task_request (~1Hz) ✅
2. **global_coverage**:
   - 收到task_request后规划路径 ✅
   - 持续发送路径(10Hz)直到收到新任务 ✅
3. **velocity_controller**:
   - 接收RTK数据 ✅
   - 接收路径(首次或新task_id时设置) ✅
   - 自动跳过已通过的路径点 ✅
   - 计算并发送速度命令 ✅
4. **sim_input**: 接收并发送速度命令到仿真器 ✅
5. **仿真器**: 机器人沿着规划路径运动 ✅

---

## 风险评估

### 低风险
- ✅ global_coverage持续发送: 符合"最新值语义"，InputPort会自动丢弃重复
- ✅ 路径版本号检测: 简单且安全

### 中等风险
- ⚠️ 路径点通过检测: 如果goal_tolerance设置不当，可能跳过点
- **缓解**: 使用较小的tolerance (0.3m)，保证精度

### 无风险
- 所有修改都是增量的，不破坏现有功能
- 可以逐步部署 (先修复global_coverage验证，再修复velocity_controller)

---

## 回滚方案

如果修复后出现问题:

```bash
# 回滚global_coverage
git checkout node-hub/global_coverage/run.py

# 回滚velocity_controller
git checkout node-hub/velocity_controller/run.py
```

---

## 附录: 测试验证清单

- [ ] global_coverage持续发送路径 (检查日志)
- [ ] velocity_controller只接收一次路径 (检查task_id)
- [ ] velocity_controller正确更新路径索引
- [ ] 机器人沿着规划路径运动
- [ ] 到达终点后停止
- [ ] 收到新task时重新规划

---

**状态**: 📝 Ready to Implement
**预计修复时间**: 10-15分钟
**验证时间**: 10分钟

