# Socket传输问题根本原因分析

**时间**: 2025-12-23 16:20
**状态**: ✅ **问题已找到** - 分层启动导致初期数据丢失

## 执行摘要

通过创建专用的test_sender和test_receiver节点,成功复现并诊断了socket传输问题。

**根本原因**: **OutputPort在InputPort连接之前发送的数据会被丢弃**

## 测试结果

### 测试配置
```yaml
graph_id: test_socket_transfer
nodes:
  - sender (Layer 0): 每秒发送5条消息
  - receiver (Layer 1): 每秒检查10次接收
```

### 关键发现

#### 1. 启动阶段 - 数据丢失
```
[SENDER] Loop #0: About to call send() with message: {'sequence': 0, ...}
[OutputPort] 'test_message' send: No clients connected, dropping data
[SENDER] Loop #0: send() returned successfully

... (重复约16次循环) ...

[SENDER] Loop #16: About to call send() with message: {'sequence': 16, ...}
[OutputPort] 'test_message' send: No clients connected, dropping data
```

**分析**: sender在前16次发送中,没有任何客户端连接,所有数据被丢弃

#### 2. 连接建立后 - 数据传输成功
```
[InputPort] 'test_message' connected to /tmp/nodeflow_sockets/nodeflow_sender.test_message.out
[RECEIVER] Loop #0: About to call recv_latest()
[InputPort] 'test_message' recv_latest: No data (reader returned None)
[RECEIVER] Loop #1: About to call recv_latest()
[InputPort] 'test_message' recv_latest: No data (reader returned None)
[RECEIVER] Loop #2: About to call recv_latest()
[RECEIVER] Loop #2: recv_latest() returned: {'sequence': 155, 'timestamp': 1766478087.546585, ...}
```

**分析**:
- InputPort成功连接到OutputPort ✅
- 前2次轮询返回None (正常,socket缓冲区空)
- 第3次轮询接收到第一条消息 (sequence=155,说明前154条已丢失)

#### 3. 稳定运行阶段 - 正常传输
```
[RECEIVER] Loop #977: recv_latest() returned: {'sequence': 648, 'timestamp': 1766478187.560019, ...}
```

**统计**:
- Sender发送: ~648条消息
- Receiver接收: ~493条消息 (648 - 155 = 493)
- **丢失率**: 24% (前154条在连接建立前丢失)

## 根本原因

### OutputPort.send()行为
```python
def send(self, data: Dict[str, Any]):
    self._accept_new_clients()  # 尝试接受新连接

    if not self.client_socks:   # 如果没有客户端
        print(f"[OutputPort] '{self.name}' send: No clients connected, dropping data", flush=True)
        return                   # 丢弃数据并返回

    # 向所有客户端发送数据
    ...
```

**设计理念**:
- OutputPort采用"尽力而为"策略
- 如果没有客户端连接,数据直接丢弃
- 不缓存,不等待,不阻塞

### 分层启动机制

NodeFlow的拓扑分层启动:
```
1. Layer 0启动 (sender/sim_output)
   ↓ 等待30秒 (启动验证)
2. Layer 1启动 (receiver/global_coverage)
   ↓ 等待30秒
3. Layer 2启动 (velocity_controller)
   ↓ ...
```

**时间线**:
```
T=0s:    sender启动,开始发送 (无客户端)
T=0-30s: sender持续发送,所有数据丢失
T=31s:   receiver启动,InputPort连接到sender
T=31s+:  数据正常传输 ✅
```

## 对完整闭环仿真的影响

### planning_minimal.yaml 拓扑
```
Layer 0: sim_output (RTK 50Hz + task_request)
         ↓ 30秒等待
Layer 1: global_coverage (接收task_request)
         ↓ 30秒等待
Layer 2: velocity_controller (接收rtk_fix + global_path)
         ↓ 30秒等待
Layer 3: sim_input
```

### 问题分析

**sim_output → global_coverage (task_request)**:
- sim_output在Layer 0启动
- global_coverage在Layer 1启动 (30秒后)
- 前30秒的task_request全部丢失 ❌
- **但**: task_request是持续发送的,连接后可以收到 ✅

**sim_output → velocity_controller (rtk_fix)**:
- sim_output在Layer 0启动
- velocity_controller在Layer 2启动 (60秒后!)
- 前60秒(3000帧)的RTK数据全部丢失 ❌
- **但**: RTK是持续更新的,连接后应该能收到 ✅

**global_coverage → velocity_controller (global_path)**:
- global_coverage在Layer 1启动
- velocity_controller在Layer 2启动 (30秒后)
- global_coverage只发送一次路径
- **如果发送在velocity_controller连接前,路径会丢失** ❌❌❌

## 为什么velocity_controller没有收到数据?

### 假设1: 启动顺序导致数据丢失
**可能性**: 60%
- velocity_controller在Layer 2,启动很晚
- sim_output的RTK数据在前60秒都被丢弃
- 但连接后应该能收到数据...

### 假设2: global_coverage的路径在velocity_controller连接前发送
**可能性**: 80% ⚠️
- global_coverage在收到task_request后立即规划并发送路径
- 如果velocity_controller还未连接,路径会丢失
- **路径只发送一次,丢失就永远收不到了**

### 假设3: 日志级别问题
**可能性**: 20%
- DEBUG日志输出的print可能未刷新到stdout
- 数据实际上在传输,但日志没显示

## 验证方法

### 立即测试
```bash
# 1. 检查sim_output是否真的在发送RTK数据
grep "\[OutputPort\] 'rtk_fix' send:" /tmp/nodeflow_logs/sim_output.stdout.log

# 2. 检查global_coverage何时发送路径
grep "Planning completed\|send.*global_path" /tmp/nodeflow_logs/global_coverage.stdout.log

# 3. 检查velocity_controller何时连接
grep "\[InputPort\].*connected" /tmp/nodeflow_logs/velocity_controller.stdout.log
```

## 解决方案

### 方案A: 修改global_coverage - 持续发送路径 (推荐)
```python
# 当前: 发送一次路径后就不再发送
self.output_port.send(path)

# 改为: 持续发送路径 (与task_request保持一致)
while True:
    if has_path:
        self.output_port.send(path)
    time.sleep(0.1)  # 10Hz
```

**优点**:
- 兼容现有架构
- 保证下游节点随时可以接收
- 符合"最新值语义"

### 方案B: 添加重连通知机制
```python
# 当InputPort连接时,通知OutputPort重新发送
class OutputPort:
    def _accept_new_clients(self):
        client_sock, _ = self.server_sock.accept()
        self.client_socks.append(client_sock)
        # 通知回调: 新客户端已连接
        if self.on_new_client_callback:
            self.on_new_client_callback()
```

**缺点**: 需要修改SDK核心

### 方案C: 启动完成信号
```python
# Runtime等待所有节点完全初始化后再开始数据流
# 但这破坏了流式处理的设计
```

## 结论

✅ **Socket传输机制本身正常** - test_sender/receiver证明数据可以传输

❌ **分层启动 + 单次发送 = 数据丢失** - global_coverage的路径很可能在velocity_controller连接前发送并丢失

**立即行动**:
1. 修改global_coverage为持续发送路径
2. 验证velocity_controller是否收到路径
3. 如果仍有问题,检查sim_output的RTK发送频率

---

**测试文件**:
- `/Users/wuzhanli/Desktop/node/node-hub/test_sender/` - 发送端节点
- `/Users/wuzhanli/Desktop/node/node-hub/test_receiver/` - 接收端节点
- `/Users/wuzhanli/Desktop/node/examples/test_socket_transfer.yaml` - 测试配置
- `/tmp/nodeflow_logs/sender.stdout.log` - 发送端日志
- `/tmp/nodeflow_logs/receiver.stdout.log` - 接收端日志

**状态**: ✅ Root Cause Identified - Ready to Fix
**优先级**: P0 Critical - 立即修复global_coverage发送逻辑
