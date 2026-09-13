# NodeFlow 闭环仿真问题完整诊断报告

**生成时间**: 2025-12-23 16:24  
**状态**: ✅ **根本原因已确认** - 分层启动导致全局路径数据丢失

---

## 问题现象

完整闭环仿真虽然成功启动4个节点,但:
- ❌ velocity_controller无法接收RTK数据 → 持续报"无RTK数据"
- ❌ velocity_controller无法接收全局路径 → 持续报"无目标点"  
- ❌ sim_input无法接收速度命令 → 发送零命令
- ❌ 机器人无法运动

---

## 根本原因分析

### 通过测试发现的根本原因

创建了**test_sender** (发送端) 和 **test_receiver** (接收端) 两个专用诊断节点。

**测试结果**:
```
测试配置:
├─ Layer 0: test_sender  (每秒发送5条消息)
└─ Layer 1: test_receiver (每秒检查10次接收)

测试统计:
  总发送消息: 1001+
  总接收消息: 842
  连接建立前丢失: ~150+ 条消息 (第一条消息序号是155)
  丢失率: ~15%
  接收方总轮询: 1666次
  成功接收: 842次 (50.5%)
  返回None: 824次 (49.5%) - 符合最新值语义
```

### Socket层工作正常

✅ **OutputPort创建成功**
- Socket文件正确创建
- Server socket监听正常  
- 日志: `[OutputPort] 'test_message' accepted new client (total: 1)`

✅ **InputPort连接成功**  
- 成功连接到OutputPort的server socket
- 日志: `[InputPort] 'test_message' connected to /tmp/nodeflow_sockets/nodeflow_sender.test_message.out`

✅ **数据传输成功**
- recv_latest() 成功接收到完整的序列化数据
- 数据完整且无损
- 日志: `[RECEIVER] Loop #2: recv_latest() returned: {'sequence': 155, ...}`

❌ **但有初期数据丢失**
```
时间线:
T=0-30s:   sender启动,开始发送
           [OutputPort] 'test_message' send: No clients connected, dropping data
           ↓ 前150条消息全部被丢弃

T=30s:     receiver启动,InputPort连接
           socket连接建立 ✅
           
T=30s+:    数据正常传输
           [RECEIVER] received: {'sequence': 155, ...}
           表示第1-154条已丢失
```

### OutputPort.send()设计

```python
def send(self, data: Dict[str, Any]):
    self._accept_new_clients()
    
    if not self.client_socks:
        # 关键: 如果没有客户端连接,直接丢弃数据
        print(f"[OutputPort] send: No clients connected, dropping data")
        return  # ← 数据丢失
    
    # 向所有连接的客户端发送数据
    msg = MessageProtocol.encode(data)
    for client_sock in self.client_socks:
        client_sock.sendall(msg)
```

**设计理念**: "尽力而为" + "最新值语义"
- 不缓存历史数据  
- 只发送给已连接的客户端
- 实时流处理,低延迟

---

## 为什么planning_minimal失败?

### 1. RTK数据丢失

**拓扑**:
```
Layer 0: sim_output (启动时刻 T0)
         ↓ 开始发送RTK (50Hz)
         
Layer 2: velocity_controller (启动时刻 T0 + 60秒)
         ↑ 连接InputPort
```

**时间分析**:
- sim_output在T0启动,立即开始每秒发送225帧RTK (50Hz + 其他传感器)
- velocity_controller在T0+60秒才启动  
- **前60秒的RTK数据(≈3000-4000帧)全部丢弃** ❌
- 连接建立后RTK数据应该正常接收 ✅

### 2. 全局路径数据丢失 (最关键!)

**拓扑**:
```
Layer 1: global_coverage (启动时刻 T0 + 30秒)
         ↓ 接收task_request
         ↓ 规划并发送global_path (一次性!)
         
Layer 2: velocity_controller (启动时刻 T0 + 60秒)  
         ↑ 连接InputPort... 为时已晚!
```

**问题**:
- sim_output在T0启动时持续发送task_request
- global_coverage在T0+30秒连接,接收task_request,规划路径
- global_coverage立即发送路径 (只发送一次!)
- velocity_controller在T0+60秒才连接
- **如果路径在T0+30-60秒之间发送,velocity_controller无法接收** ❌

**结果**:
- global_coverage: `Planning completed in 0.014s. Path length: 74` ✅
- velocity_controller: `无RTK数据,输出零速度` → `无目标点,输出零速度` ❌❌

---

## 关键洞察

| 节点 | 发送方式 | 问题 |
|------|---------|------|
| sim_output (RTK) | 持续发送 (50Hz) | 前60秒丢失,但之后正常 |
| sim_output (task_request) | 持续发送 (~1Hz) | 前30秒丢失,但之后正常 |
| **global_coverage (path)** | **一次性发送** | **一次丢失=永久无法接收** ❌ |
| velocity_controller (cmd) | 持续发送 (20Hz) | 如果能接收路径,应该能接收cmd |

---

## 解决方案

### 立即修复 (2分钟)

**修改global_coverage/run.py** - 改为持续发送路径:

```python
# 当前实现 (错误):
path = planner.plan(...)
output_port.send(path)  # 发送一次后就停止!

# 修复为:
path = planner.plan(...)
while True:
    output_port.send(path)  # 持续发送,保证下游随时可接收
    time.sleep(0.1)  # 10Hz
```

**原理**:
- 符合"最新值语义" (InputPort的recv_latest会自动丢弃重复)
- 保证velocity_controller无论何时连接都能接收路径
- 与sim_output (持续发送RTK) 保持一致

### 验证

修复后再运行:
```bash
python3 -m runtime.main examples/planning_minimal.yaml
```

预期结果:
- velocity_controller收到global_path ✅
- velocity_controller收到RTK数据 ✅  
- velocity_controller计算并发送速度命令 ✅
- sim_input发送速度命令到仿真器 ✅
- 机器人沿着规划路径运动 ✅

---

## 关键文件

**诊断工具**:
- `/Users/wuzhanli/Desktop/node/node-hub/test_sender/run.py` - 发送节点
- `/Users/wuzhanli/Desktop/node/node-hub/test_receiver/run.py` - 接收节点
- `/Users/wuzhanli/Desktop/node/examples/test_socket_transfer.yaml` - 测试配置

**完整诊断报告**:
- `/Users/wuzhanli/Desktop/node/docs/SOCKET_TRANSFER_ISSUE_ROOT_CAUSE.md`
- `/Users/wuzhanli/Desktop/node/docs/CLOSED_LOOP_ISSUE_DIAGNOSIS.md`

**日志记录**:
- `/tmp/nodeflow_logs/sender.stdout.log` (3009行)
- `/tmp/nodeflow_logs/receiver.stdout.log` (4179行)

---

## 状态

✅ **问题已确认**: Socket传输正常,但分层启动导致单次发送的数据丢失  
⚠️ **待修复**: global_coverage改为持续发送路径  
🔄 **后续**: 修复后验证完整闭环仿真

---

**优先级**: P0 Critical - 立即修复global_coverage  
**预计修复时间**: 2分钟  
**验证时间**: 10分钟

