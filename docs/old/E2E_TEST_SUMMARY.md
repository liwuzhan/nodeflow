# NodeFlow 端到端测试 - 准备就绪总结

**日期**: 2025-12-25
**状态**: ✅ 所有组件已就绪，可以运行完整的E2E测试

---

## 📋 组件清单（19/19 ✓）

### 节点库 (5个节点)
- ✅ `sim_output` - 仿真器输出节点（传感器数据 + 地块信息）
- ✅ `global_coverage` - 全覆盖路径规划节点（往复式扫描算法）
- ✅ `velocity_controller` - 速度控制节点（Pure Pursuit算法）
- ✅ `sim_input` - 仿真器输入节点（控制命令发送）
- ✅ `trajectory_viz` - 轨迹可视化节点（轨迹对比）

### 配置文件 (3个)
- ✅ `examples/planning_simulation.yaml` - 完整E2E配置
- ✅ `simulator/config.yaml` - 仿真器配置
- ✅ `simulator/server.py` - 仿真器服务器实现

### 测试工具 (2个)
- ✅ `tests/e2e_test_planning_simulation.py` - 自动化E2E测试脚本
- ✅ `tests/e2e_verify_components.sh` - 组件验证脚本

### 文档 (2个)
- ✅ `docs/E2E_TESTING_GUIDE.md` - 完整E2E测试指南
- ✅ `docs/E2E_TEST_SUMMARY.md` - 本文档

### 运行时框架 (4个核心组件)
- ✅ `runtime/main.py` - 运行时主程序
- ✅ `runtime/orchestrator/startup_coordinator.py` - 启动协调器
- ✅ `runtime/orchestrator/node_launcher.py` - 节点启动器
- ✅ `sdk/nodeflow_sdk.py` - NodeFlow SDK

### 已有测试 (3个测试套件)
- ✅ `velocity_controller/test/` - 54个测试（单元 + 集成）
- ✅ `global_coverage/test/` - 39个测试（单元 + 集成）
- ✅ `trajectory_viz/test/` - 34个测试（参考实现）

---

## 🎯 测试流程架构

```
┌───────────────────────────────────────────────────────────────┐
│                      完整闭环测试架构                           │
└───────────────────────────────────────────────────────────────┘

外部仿真器 (localhost:5555)
    │
    ↓ ZMQ REQ/REP
    │
┌───▼────────────────────────────────────────────────────────┐
│  sim_output (仿真器输出节点)                                │
│  - 读取地块、车辆配置 (初始化1次)                           │
│  - 读取RTK定位 (持续50Hz)                                   │
└───┬──────────────────────────────┬──────────────────────────┘
    │                              │
    │ task_request                 │ rtk_fix (50Hz)
    │ (地块+车辆)                   │
    │                              │
┌───▼──────────────┐        ┌─────▼─────────────────────────┐
│ global_coverage  │        │   velocity_controller         │
│ (全覆盖规划)      │        │   (Pure Pursuit控制)          │
│ - 算法: 往复扫描  │        │   输入1: RTK定位              │
│ - 输出: 路径点    │        │   输入2: 全局路径 ←──────────┼─┐
└───┬──────────────┘        └─────┬─────────────────────────┘ │
    │ global_path (1次)            │ velocity_cmd (20Hz)       │
    └──────────────────────────────┼───────────────────────────┘
                                   │
                            ┌──────▼──────────┐
                            │   sim_input     │
                            │ (控制命令输入)  │
                            └──────┬──────────┘
                                   │
                                   ↓ ZMQ REQ/REP
                            外部仿真器 (更新位置)
                                   │
                                   └──→ 闭环反馈

┌────────────────────────────────────────────────────────────┐
│  trajectory_viz (可视化节点)                                │
│  输入: task_request + global_path + rtk_fix               │
│  输出: logs/jpg/*.jpg (轨迹对比图)                         │
└────────────────────────────────────────────────────────────┘
```

**数据格式**:
- `task_request`: `planning.task` - 地块（多边形）+ 车辆配置
- `rtk_fix`: `json` - RTK GPS定位（lat, lon, heading, status）
- `global_path`: `planning.path` - WGS84路径点列表
- `velocity_cmd`: `json` - 线速度 + 角速度

---

## 🚀 快速开始

### 方法1：使用自动化测试脚本（推荐）

```bash
# 运行完整的E2E测试（自动启动仿真器和运行时）
python3 tests/e2e_test_planning_simulation.py
```

**测试内容**:
- ✓ 启动仿真器服务器
- ✓ 启动NodeFlow运行时（5个节点）
- ✓ 验证数据流（RTK → 控制命令）
- ✓ 验证控制循环（闭环运行）
- ✓ 验证可视化输出（生成轨迹对比图）

**预期输出**:
```
==================================================================
【测试1】仿真器启动
==================================================================
✓ 仿真器响应正常

==================================================================
【测试2】运行时和节点启动
==================================================================
✓ PID文件创建: <pid>

==================================================================
【测试3】数据流验证
==================================================================
✓ 数据流验证完成

==================================================================
【测试4】控制循环
==================================================================
✓ 控制循环运行

==================================================================
【测试5】可视化输出
==================================================================
生成的JPG文件数: X
  - trajectory_comparison_<timestamp>.jpg
✓ 可视化文件已生成

==================================================================
【测试结果汇总】
==================================================================
✓ simulator_startup: PASSED
✓ runtime_startup: PASSED
✓ data_flow: PASSED
✓ control_loop: PASSED
✓ visualization: PASSED
==================================================================
总计: 5 | 通过: 5 | 失败: 0
==================================================================
```

---

### 方法2：手动运行（用于调试）

**终端1 - 启动仿真器**:
```bash
cd /Users/wuzhanli/Desktop/node
python3 simulator/server.py
```

预期输出：
```
仿真器服务器启动在 localhost:5555
等待连接...
```

**终端2 - 启动运行时**:
```bash
cd /Users/wuzhanli/Desktop/node
python3 -m runtime.main examples/planning_simulation.yaml
```

预期输出：
```
============================================================
NodeFlow Runtime Starting
============================================================
Loading configuration from: examples/planning_simulation.yaml
Graph ID: planning_simulation
Graph Version: 1.0

=== Starting Layer 0 (1 nodes) ===
Nodes: ['sim_output']
✓ Node 'sim_output' started successfully

=== Starting Layer 1 (1 nodes) ===
Nodes: ['global_coverage']
✓ Node 'global_coverage' started successfully

=== Starting Layer 2 (2 nodes) ===
Nodes: ['velocity_controller', 'sim_input']
✓ Node 'velocity_controller' started successfully
✓ Node 'sim_input' started successfully

=== Starting Layer 3 (1 nodes) ===
Nodes: ['trajectory_viz']
✓ Node 'trajectory_viz' started successfully

============================================================
All 5 nodes started successfully
============================================================
Runtime is RUNNING
Press Ctrl+C to stop
============================================================
```

**监控运行**:
```bash
# 终端3 - 查看节点进程
watch -n 1 'ps aux | grep -E "sim_output|global_coverage|velocity|sim_input|trajectory"'

# 终端4 - 查看可视化输出
watch -n 10 'ls -lh logs/jpg/'
```

**停止运行**:
- 在终端2按 `Ctrl+C` 停止运行时（会自动逐个关闭节点）
- 在终端1按 `Ctrl+C` 停止仿真器

---

## 📊 验证清单

### 启动验证
- [ ] 仿真器在 `localhost:5555` 监听
- [ ] 5个节点按拓扑顺序启动
- [ ] PID文件创建在 `/tmp/nodeflow_runtime.pid`
- [ ] 没有启动错误

### 数据流验证
- [ ] `sim_output` 输出 RTK 定位（50Hz）
- [ ] `global_coverage` 输出规划路径（初始1次）
- [ ] `velocity_controller` 输出速度命令（20Hz）
- [ ] `sim_input` 发送控制到仿真器

### 闭环验证
- [ ] RTK定位 → 控制器（延迟 <10ms）
- [ ] 控制器 → 仿真器（延迟 <20ms）
- [ ] 仿真器更新位置（延迟 <10ms）
- [ ] 完整循环时间 ~50-100ms

### 可视化验证
- [ ] `logs/jpg/` 目录存在
- [ ] 至少生成1个轨迹对比图
- [ ] 图像显示：规划路径（蓝色）vs 实际轨迹（红色）

---

## 📁 生成的文件

### 日志文件
```
logs/
├── nodeflow.log               # 运行时日志
├── nodeflow_errors.log        # 错误日志（如有）
└── jpg/
    └── trajectory_comparison_*.jpg  # 轨迹对比图
```

### 临时文件
```
/tmp/
├── nodeflow_runtime.pid       # PID文件
└── nodeflow_sockets/          # Socket通信文件
    ├── nodeflow_sim_output.rtk_fix.out
    ├── nodeflow_global_coverage.global_path.out
    └── ...
```

---

## 🔧 调试技巧

### 查看实时日志
```bash
# 运行时主日志
tail -f logs/nodeflow.log

# 仿真器日志
tail -f simulator/server.log

# 特定节点日志（如有）
tail -f /tmp/nodeflow_logs/velocity_controller.stdout.log
```

### 增加调试输出
编辑 `examples/planning_simulation.yaml`:
```yaml
# 启用更多传感器
sim_output:
  enable_state: true     # 启用状态调试
  enable_imu: true       # 启用IMU数据

# 增加日志级别
# 运行时使用：
python3 -m runtime.main examples/planning_simulation.yaml --log-level DEBUG
```

### 验证Socket连接
```bash
# 查看ZMQ连接
netstat -an | grep 5555

# 查看Unix Socket
ls -la /tmp/nodeflow_sockets/

# 验证节点进程
ps aux | grep -E "sim_output|global|velocity|sim_input|trajectory" | grep -v grep
```

---

## 🎓 学习路径

### 1. 理解配置文件
阅读 `examples/planning_simulation.yaml`，理解：
- 节点定义（nodes）
- 数据连接（edges）
- 参数配置（params）

### 2. 理解节点实现
阅读关键节点的实现：
- `node-hub/sim_output/run.py` - 传感器输出
- `node-hub/global_coverage/run.py` - 路径规划
- `node-hub/velocity_controller/run.py` - 控制算法

### 3. 理解运行时
阅读运行时框架：
- `runtime/main.py` - 主入口
- `runtime/orchestrator/startup_coordinator.py` - 节点启动顺序
- `sdk/nodeflow_sdk.py` - SDK接口

### 4. 修改和扩展
尝试修改：
- 车辆参数（作业幅宽、速度等）
- 控制参数（前瞻距离、增益等）
- 添加新的数据连接或节点

---

## 📚 相关文档

| 文档 | 路径 | 用途 |
|------|------|------|
| **E2E测试指南** | `docs/E2E_TESTING_GUIDE.md` | 详细的测试说明和故障排查 |
| **测试脚本** | `tests/e2e_test_planning_simulation.py` | 自动化测试实现 |
| **配置文件** | `examples/planning_simulation.yaml` | 完整的E2E配置 |
| **仿真器文档** | `simulator/README.md` | 仿真器使用说明 |
| **节点测试指南** | `docs/NODE_TESTING_GUIDE.md` | 单节点测试规范 |

---

## ✅ 下一步

准备就绪！现在可以：

1. **快速验证**: `python3 tests/e2e_test_planning_simulation.py`
2. **手动测试**: 按照上面的"方法2"分别启动仿真器和运行时
3. **查看文档**: `cat docs/E2E_TESTING_GUIDE.md`
4. **修改配置**: 编辑 `examples/planning_simulation.yaml` 尝试不同的参数
5. **添加节点**: 在 `node-hub/` 创建新节点并添加到配置中

---

**状态**: ✅ 已就绪
**组件**: 19/19 ✓
**测试**: 准备运行
**文档**: 完整齐全

🎉 **一切准备就绪，可以开始端到端测试！**
