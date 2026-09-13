# NodeFlow 闭环仿真数据流断裂问题诊断报告

**时间**: 2025-12-23 14:52
**状态**: 🔴 **关键问题已发现** - 数据未通过socket传输

## 执行摘要

完整闭环仿真已成功启动,4个节点全部运行,但**数据流在socket层面断裂**:
- ✅ 所有节点进程启动成功
- ✅ 所有输入输出端口创建成功
- ✅ Socket连接建立成功
- ❌ **OutputPort.send()未发送任何数据到已连接的客户端**

## 问题现象

### 运行结果
- **sim_output**: 每秒输出~225帧RTK数据(持续运行6000+帧)
- **global_coverage**: 成功规划74点路径
- **velocity_controller**: 持续报错"无RTK数据,输出零速度"(每秒20次)
- **sim_input**: 接收不到velocity命令,发送零命令

### 关键日志输出

```
[OutputPort] 'task_request' accepted new client (total: 1)
[InputPort] 'task_request' connected to /tmp/nodeflow_sockets/nodeflow_sim_output.task_request.out
[InputPort] 'task_request' recv_latest: No data (reader returned None)
```

**问题分析**:
1. OutputPort正确创建server socket并接受连接 ✅
2. InputPort正确连接到OutputPort的socket ✅
3. **但recv_latest()返回None** - 说明没有收到数据 ❌

## 根本原因

### 假设1: OutputPort.send()未被调用
**状态**: 待验证
- 需要检查是否添加了"[OutputPort] send: ..."日志

### 假设2: send()收到零客户端连接
**状态**: 否决
日志显示"accepted new client (total: 1)",说明确实有客户端连接

### 假设3: 数据被丢弃在缓冲区中
**状态**: 调查中
OutputPort.send()有两种情况:
- 客户端缓冲区满时丢弃消息(BlockingIOError)
- 客户端断开连接时移除

## 架构现状

### 拓扑结构(4层)
```
Layer 0: sim_output
    ├─ Output: rtk_fix (50Hz)
    └─ Output: task_request (1Hz+)

Layer 1: global_coverage
    ├─ Input: task_request ←← [已连接✅]
    └─ Output: global_path

Layer 2: velocity_controller
    ├─ Input: rtk_fix ←← [已连接✅]
    ├─ Input: global_path ←← [已连接✅]
    └─ Output: velocity_cmd

Layer 3: sim_input
    └─ Input: velocity_cmd ←← [已连接✅]
```

### Socket连接验证
```
已创建的socket文件:
  /tmp/nodeflow_sockets/nodeflow_sim_output.rtk_fix.out
  /tmp/nodeflow_sockets/nodeflow_sim_output.task_request.out
  /tmp/nodeflow_sockets/nodeflow_global_coverage.global_path.out
  /tmp/nodeflow_sockets/nodeflow_velocity_controller.velocity_cmd.out

已建立的连接:
  global_coverage → sim_output.task_request ✅
  velocity_controller → sim_output.rtk_fix ✅ (假设)
  velocity_controller → global_coverage.global_path ✅ (假设)
  sim_input → velocity_controller.velocity_cmd ✅ (假设)
```

## 代码修改跟踪

已为诊断目的添加的debug输出:

### port.py 改动
```python
# OutputPort._accept_new_clients() - 第79行
print(f"[OutputPort] '{self.name}' accepted new client (total: {len(self.client_socks)})", flush=True)

# OutputPort.send() - 第108-111行
if not self.client_socks:
    print(f"[OutputPort] '{self.name}' send: No clients connected, dropping data", flush=True)
    return
print(f"[OutputPort] '{self.name}' send: sending to {len(self.client_socks)} clients", flush=True)

# InputPort._connect() - 第230行
print(f"[InputPort] '{self.name}' connected to {self.socket_path}", flush=True)

# InputPort.recv_latest() - 第342, 347, 353行
print(f"[InputPort] '{self.name}' recv_latest: reader={...}, sock={...}", flush=True)
print(f"[InputPort] '{self.name}' recv_latest: connection check failed", flush=True)
print(f"[InputPort] '{self.name}' recv_latest: No data (reader returned None)", flush=True)
```

### 节点debug logging - 已启用
- sim_output: `NodeFlowSDK(log_level="DEBUG")`
- global_coverage: `NodeFlowSDK(log_level="DEBUG")`
- velocity_controller: `NodeFlowSDK(log_level="DEBUG")`
- sim_input: `NodeFlowSDK(log_level="DEBUG")`

## 下一步诊断

### 待验证的问题
1. **OutputPort.send()是否被调用?**
   - 检查日志中是否有"[OutputPort] 'rtk_fix' send: sending to X clients"

2. **为什么InputPort.recv_latest()返回None?**
   - 虽然socket已连接,但没有数据
   - 可能原因:
     - send()从不被调用
     - send()立即返回(无客户端/缓冲区满)
     - 数据被丢弃

3. **MessageProtocol.decode()是否工作?**
   - 检查数据是否被正确序列化和反序列化

### 建议的调试步骤

```bash
# 1. 启用更详细的输出
grep "\[OutputPort\] 'rtk_fix'" /tmp/nodeflow_logs/*.log

# 2. 检查sim_output是否调用了send()
grep "send\|Send" /tmp/nodeflow_logs/sim_output.stdout.log

# 3. 监控socket文件的activity
lsof /tmp/nodeflow_sockets/nodeflow_sim_output.rtk_fix.out

# 4. 使用strace跟踪socket调用(如果需要)
strace -e sendto,recvfrom python3 -m runtime.main examples/planning_minimal.yaml
```

## 性能指标

```
时间轴:
  14:46:04 - sim_output启动
  14:47:07 - velocity_controller启动 (~63秒后)
  14:48:40 - 已运行~100秒

数据量:
  sim_output: 6939帧 / 100秒 = 69.39 FPS (配置50Hz)
  global_coverage: 74点规划
  velocity_controller: 0个有效命令(无RTK数据)
  sim_input: 0个速度命令
```

## 相关文件

**日志文件**:
- `/tmp/nodeflow_logs/sim_output.std{out,err}.log` - 发送方日志
- `/tmp/nodeflow_logs/global_coverage.std{out,err}.log` - 接收方日志
- `/tmp/nodeflow_logs/velocity_controller.std{out,err}.log` - 接收方日志

**源代码**:
- `/Users/wuzhanli/Desktop/node/sdk/port.py` - InputPort/OutputPort实现
- `/Users/wuzhanli/Desktop/node/sdk/nodeflow_sdk.py` - SDK初始化
- `/Users/wuzhanli/Desktop/node/runtime/ipc/socket_manager.py` - Socket管理

**配置文件**:
- `/Users/wuzhanli/Desktop/node/examples/planning_minimal.yaml` - 运行配置

## 结论

系统框架和基础设施正常,但存在**socket数据传输层的关键缺陷**:

- ✅ 进程管理: 正常
- ✅ 配置和拓扑: 正确
- ✅ Socket连接: 成功建立
- ❌ **数据传输: 断裂** ← **需要立即修复**

需要立即调查OutputPort.send()为何未能通过socket发送数据给已连接的InputPort。

---

**状态**: 🔴 Critical Issue Detected - Ready for Deep Debugging
**优先级**: P0 Blocker
