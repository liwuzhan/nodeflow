# Logger测试 - 验证数据流

## 快速开始（3步）

### 步骤1: 启动仿真器

```bash
# 终端1
cd /Users/wuzhanli/Desktop/node/simulator
python3 server.py
```

等待看到启动成功的消息。

### 步骤2: 运行Logger测试

```bash
# 终端2
cd /Users/wuzhanli/Desktop/node
python3 test_with_logger.py
```

### 步骤3: 打开浏览器查看Logger

在浏览器中打开: **http://localhost:8001**

你会看到实时的数据流！

---

## 数据流说明

```
仿真器 (ZMQ Server :5555)
    ↓
sim_rtk (读取RTK GPS)
    ↓ rtk_fix
    ├→ velocity_controller (纯追踪算法)
    │      ↓ velocity_cmd
    │      ├→ sim_velocity (发送速度命令)
    │      │
    │      └→ Logger.input2 (记录速度命令) ✓
    │
    └→ Logger.input1 (记录RTK数据) ✓
```

## Logger会记录什么？

### Input1 (RTK GPS数据)
每条数据包含：
```json
{
  "timestamp": 1703255401.123,
  "port": "input1",
  "data": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "altitude": 10.5,
    "rtk_status": "FIXED",
    "accuracy_h": 0.02,
    "num_satellites": 14
  }
}
```

### Input2 (速度命令)
每条数据包含：
```json
{
  "timestamp": 1703255401.125,
  "port": "input2",
  "data": {
    "linear_velocity": 0.85,
    "angular_velocity": 0.15,
    "distance_to_goal": 5.2,
    "heading_error_deg": 8.5
  }
}
```

## 验证清单

在Logger Web界面中检查：

- [ ] **input1频率**: 约20Hz (RTK GPS)
- [ ] **input2频率**: 约20Hz (控制器)
- [ ] **RTK状态**: 大部分应该是FIXED (85%)
- [ ] **速度范围**: linear_velocity在0~1.0 m/s
- [ ] **时间戳**: 递增且无跳变
- [ ] **数据完整性**: 每条数据都有必需字段

## 常见数据问题排查

### 问题1: input1无数据（RTK GPS）

**可能原因**:
- sim_rtk节点未启动
- 仿真器RTK频率限制 (>20Hz)
- ZMQ连接失败

**检查方法**:
```bash
# 直接查询仿真器
curl -X POST http://localhost:5555 -d '{"type":"get_sensor","sensor":"rtk_gps"}'
```

### 问题2: input2无数据（速度命令）

**可能原因**:
- velocity_controller未收到RTK数据
- 没有设置目标点或路径
- 控制器参数enable_control=false

**检查方法**:
查看velocity_controller的日志，是否输出"无目标点"警告。

### 问题3: 时间戳不对齐

**可能原因**:
- 节点运行在不同频率
- 系统时间跳变

**正常情况**:
- RTK和速度命令的时间戳应该非常接近（<50ms）
- 因为控制器收到RTK后立即计算速度命令

### 问题4: RTK状态总是SINGLE或NONE

这是仿真器的正常行为，RTK状态分布：
- FIXED: 85%
- FLOAT: 10%
- SINGLE: 4%
- NONE: 1%

如果长时间看到NONE，说明GPS仿真可能有问题。

## Logger Web界面功能

打开 http://localhost:8001 后你可以：

1. **实时查看日志**: 自动滚动显示新数据
2. **过滤端口**: 点击"input1"、"input2"按钮显示/隐藏特定端口
3. **搜索关键字**: 在搜索框输入，如"FIXED"只显示RTK固定解的数据
4. **导出日志**: 点击Export按钮下载JSON文件
5. **清空日志**: 点击Clear清空内存缓冲

## 导出的日志文件

日志会自动保存到：`./logs/simulation.jsonl`

查看日志：
```bash
# 查看最新20条
tail -20 logs/simulation.jsonl

# 格式化查看
cat logs/simulation.jsonl | python3 -m json.tool | head -50

# 统计RTK状态分布
cat logs/simulation.jsonl | grep input1 | jq '.data.rtk_status' | sort | uniq -c
```

## 高级：完整工作流测试

如果你想测试真实的闭环控制（不只是采样数据），可以使用：

```bash
# 运行完整的NodeFlow工作流 (假设你有nodeflow CLI)
nodeflow run test_with_logger.yaml

# 在另一个终端发送目标点
python3 -c "
from sdk.nodeflow_sdk import NodeFlowSDK
with NodeFlowSDK() as sdk:
    sdk.send('target_point', {
        'latitude': 40.7130,
        'longitude': -74.0062
    })
    print('✓ 目标点已发送')
"
```

然后在Logger Web界面观察：
- input1: RTK位置逐渐接近目标
- input2: 速度命令根据距离调整（远离时快，接近时慢）
- distance_to_goal: 逐渐减小到0.3m以下

## 预期结果

如果一切正常，你应该看到：

```
[终端输出]
✓ RTK数据采集: 10/10 成功
  RTK状态分布:
    FIXED: 9/10 (90%)
    FLOAT: 1/10 (10%)

✓ 速度命令执行: 10/10 成功

✓ 所有数据流验证通过！

[浏览器Logger界面]
- 每秒约20条input1日志（RTK GPS）
- 每秒约20条input2日志（速度命令）
- 时间戳递增
- 数据格式正确

[日志文件]
$ wc -l logs/simulation.jsonl
200 logs/simulation.jsonl  # 10秒 × 20Hz = 200条
```

## 故障排除

### Logger端口被占用

```yaml
# 修改 test_with_logger.yaml
params:
  web_port: 8002  # 改为其他端口
```

### 依赖安装

```bash
cd node-hub/logger
pip3 install -r requirements.txt
```

### 清理旧日志

```bash
rm -f logs/simulation.jsonl
mkdir -p logs
```

---

## 总结

Logger测试的目的是验证：

1. ✓ RTK GPS数据正确从仿真器流向控制器
2. ✓ 控制器正确计算速度命令
3. ✓ 速度命令正确发送给执行器
4. ✓ 所有数据格式符合预期
5. ✓ 时间戳和频率正确

如果这个测试通过，说明你的完整数据流是正确的！🎉
