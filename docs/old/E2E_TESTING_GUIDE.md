# NodeFlow 端到端集成测试指南

## 概述

完整的农田覆盖规划和控制闭环测试：**仿真器 → 传感器输出 → 规划器 → 控制器 → 仿真器输入 → 仿真器**

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        仿真器服务器                              │
│                   (simulator/server.py)                         │
│                  localhost:5555 (ZMQ)                          │
└───────────────────────────────────────────────────────────────┬─┘
                                                                    │
                                                    ┌───────────────┘
                                                    │
                    ┌───────────────────────────────▼──────────────┐
                    │         sim_output (仿真器输出)               │
                    │  读取：地块、车辆配置、RTK定位（50Hz）      │
                    └───────┬──────────────────────────────────────┘
                            │
                    ┌───────┴──────────────┬──────────────────────┐
                    │                      │                      │
            ┌───────▼──────┐     ┌────────▼──────┐      ┌────────▼──────┐
            │ task_request │     │   rtk_fix     │      │   task_request │
            │  (地块+车辆)  │     │  (定位数据)    │      │  (规划输入)    │
            │              │     │               │      │               │
            └───────┬──────┘     └────────┬──────┘      └────────┬──────┘
                    │                     │                      │
                    │                     │                  ┌───▼──────────┐
                    │                     │                  │              │
            ┌───────▼────────┐    ┌──────┘            ┌──────▼─────────┐   │
            │global_coverage │    │                   │trajectory_viz  │   │
            │   (规划器)       │    │                   │  (可视化)      │   │
            │  往复式扫描算法  │    │                   │                │   │
            └───────┬────────┘    │                   └────────────────┘   │
                    │             │                                        │
            ┌───────▼──────┐      │                                        │
            │global_path   │      │                                        │
            │(规划路径)     │      │                                        │
            └───────┬──────┘      │                                        │
                    │             │                                        │
                    │     ┌───────┴────────┐                              │
                    │     │                │                              │
                    │  ┌──▼───────────────▼──────────────┐                │
                    │  │  velocity_controller (控制器)    │                │
                    │  │  Pure Pursuit算法                │                │
                    │  │  输入: RTK定位 + 规划路径        │                │
                    │  │  输出: 线速度 + 角速度           │                │
                    │  └──┬──────────────────────────────┘                │
                    │     │                                              │
                    │  ┌──▼──────────────────┐                          │
                    │  │ velocity_cmd       │                          │
                    │  │ (控制命令)          │                          │
                    │  └──┬──────────────────┘                          │
                    │     │                                              │
                    │     └────────────────────────────┐                │
                    │                                  │                │
                    └──────────────────────────────────┼────────────────┘
                                                       │
                                            ┌──────────▼─────────┐
                                            │   sim_input        │
                                            │  (仿真器输入)       │
                                            │  发送控制命令      │
                                            └──────────┬─────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │   仿真器更新        │
                                            │   位置和状态        │
                                            └────────────────────┘
```

## 测试流程

### 前置条件

1. **项目结构完整**:
   ```
   /node/
   ├── simulator/              # 仿真器
   │   └── server.py          # 仿真器服务器
   ├── runtime/               # 运行时框架
   ├── node-hub/              # 节点库
   │   ├── sim_output/        # 传感器输出节点
   │   ├── global_coverage/   # 规划节点
   │   ├── velocity_controller/ # 控制节点
   │   ├── sim_input/         # 仿真器输入节点
   │   └── trajectory_viz/    # 可视化节点
   └── examples/
       └── planning_simulation.yaml  # E2E配置文件
   ```

2. **依赖包安装**:
   ```bash
   pip3 install zmq pyyaml numpy
   ```

### 运行E2E测试

#### 方法1：使用测试脚本（推荐）

```bash
# 方法A：直接运行测试脚本
python3 tests/e2e_test_planning_simulation.py

# 方法B：使用pytest运行
python3 -m pytest tests/e2e_test_planning_simulation.py -v

# 方法C：带调试输出
python3 tests/e2e_test_planning_simulation.py --verbose
```

#### 方法2：手动运行各个组件

**终端1：启动仿真器**
```bash
python3 simulator/server.py
```

**终端2：启动运行时**
```bash
python3 -m runtime.main examples/planning_simulation.yaml
```

**监控输出**：运行时会：
1. 启动所有5个节点：sim_output → global_coverage → velocity_controller → sim_input + trajectory_viz
2. 开始数据流循环（50Hz RTK输出 × 20Hz控制）
3. 生成可视化文件到 `logs/jpg/`

### 测试验证点

#### 1. 仿真器启动（Test1）
```
✓ 仿真器进程启动成功
✓ ZMQ服务器在 localhost:5555 监听
✓ ping 命令返回成功
```

#### 2. 运行时和节点启动（Test2）
```
✓ NodeFlow运行时进程启动
✓ 所有5个节点依次启动（按拓扑顺序）
✓ PID文件创建在 /tmp/nodeflow_runtime.pid
✓ Socket通信建立成功
```

#### 3. 数据流验证（Test3）
```
✓ sim_output 持续输出 RTK 定位数据（50Hz）
✓ sim_output 发送 task_request 给 global_coverage
✓ global_coverage 返回规划路径
✓ velocity_controller 接收路径和RTK定位
✓ velocity_controller 计算并输出速度命令
```

#### 4. 控制循环（Test4）
```
✓ RTK定位 → 速度控制器 (延迟 <10ms)
✓ 速度控制器 → 仿真器 (延迟 <20ms)
✓ 仿真器更新位置 (延迟 <10ms)
✓ 闭环周期 ~50-100ms
```

#### 5. 可视化输出（Test5）
```
✓ trajectory_viz 生成对比图像
✓ 图像显示：规划路径 vs 实际轨迹
✓ 文件保存在 logs/jpg/ 目录
✓ 支持导出和复盘分析
```

## 配置说明

配置文件位置：`examples/planning_simulation.yaml`

### 关键参数

#### sim_output 仿真器输出配置
```yaml
simulator_host: localhost      # 仿真器主机
simulator_port: 5555           # 仿真器端口
output_frequency: 50.0         # 输出频率 50Hz
enable_rtk: true              # 启用RTK定位
implement_width_m: 3.0         # 作业幅宽 3m
overlap_ratio: 0.1             # 行重叠 10%
```

#### velocity_controller 控制器配置
```yaml
max_speed: 1.0                # 最大线速度 1 m/s
min_speed: 0.2                # 最小线速度 0.2 m/s
lookahead_distance: 2.0       # Pure Pursuit 前瞻距离
goal_tolerance: 0.3           # 目标到达容差 0.3m
control_frequency: 20         # 控制频率 20Hz
```

#### trajectory_viz 可视化配置
```yaml
output_dir: ./logs/jpg         # 输出目录
image_format: jpg              # 图像格式
update_interval: 10.0          # 每10秒更新一次
dpi: 150                       # 图像质量
```

## 数据流说明

### 坐标系统

所有坐标使用 **WGS84 GPS坐标** (经度, 纬度)：
- sim_output: 仿真器笛卡尔坐标 → WGS84 转换
- global_coverage: WGS84 地块 → 规划路径（WGS84）
- velocity_controller: WGS84 位置 + 路径 → 速度命令
- trajectory_viz: WGS84 地块、路径、轨迹 → 可视化

### 数据频率

| 节点 | 端口 | 频率 | 说明 |
|------|------|------|------|
| sim_output | rtk_fix | 50Hz | RTK定位数据 |
| sim_output | task_request | 1次 | 地块+车辆配置（初始化） |
| global_coverage | global_path | 1次 | 规划路径 |
| velocity_controller | velocity_cmd | 20Hz | 速度命令 |
| trajectory_viz | - | 10s | 生成可视化文件 |

### 缓冲区配置

| 节点 | 缓冲区大小 | 模式 | 说明 |
|------|----------|------|------|
| sim_output | 默认 | 覆盖 | 只保留最新传感器数据 |
| global_coverage | 1MB | 覆盖 | 覆盖之前的规划结果 |
| velocity_controller | 默认 | 覆盖 | 只保留最新控制命令 |
| trajectory_viz | 默认 | 追加 | 累积轨迹数据用于可视化 |

## 故障排查

### 常见问题

#### 1. 仿真器连接失败
```
错误：zmq.error.Again: Resource temporarily unavailable
原因：仿真器未启动或端口不对
解决：
  1. 检查仿真器进程: ps aux | grep server.py
  2. 检查端口: netstat -an | grep 5555
  3. 重启仿真器: python3 simulator/server.py
```

#### 2. 节点启动超时
```
错误：NodeStartupError: Node 'global_coverage' startup timeout
原因：节点依赖关系或资源不足
解决：
  1. 检查日志: tail -f logs/nodeflow.log
  2. 增加超时: --startup-timeout 60
  3. 检查Socket权限: ls -la /tmp/nodeflow_sockets/
```

#### 3. 数据未流动
```
错误：没有看到rtk_fix或velocity_cmd输出
原因：Socket未正确连接或数据超时
解决：
  1. 使用 --verbose 启用调试日志
  2. 检查边配置: cat examples/planning_simulation.yaml | grep edges
  3. 验证Socket连接: netstat -an | grep nodeflow
```

#### 4. 可视化文件未生成
```
错误：logs/jpg/ 目录为空
原因：trajectory_viz 未收到数据或超时
解决：
  1. 检查 trajectory_viz 是否启动
  2. 增加运行时长: python3 tests/e2e_test_planning_simulation.py --duration 60
  3. 检查磁盘空间: df -h
```

## 性能指标

### 期望性能

| 指标 | 目标 | 说明 |
|------|------|------|
| RTK 输出延迟 | <10ms | 从仿真器到 velocity_controller |
| 控制命令延迟 | <20ms | 从 velocity_controller 到 sim_input |
| 完整循环时间 | 50-100ms | RTK → 控制 → 仿真器更新 → RTK |
| 规划时间 | <1s | 单次全覆盖路径规划 |
| 内存占用 | <50MB | 整个运行时的总内存 |

### 监控

运行时期间可监控：
```bash
# 终端另外打开监控
watch -n 1 'ps aux | grep -E "sim_output|global_coverage|velocity|sim_input|trajectory"'
```

## 扩展和修改

### 修改仿真场景

编辑 `examples/planning_simulation.yaml`:

1. **改变地块大小**：修改 `simulator/config.yaml`
2. **改变车辆参数**：修改 `sim_output.implement_width_m` 等
3. **改变控制速度**：修改 `velocity_controller.max_speed` 等
4. **启用更多传感器**：设置 `sim_output.enable_imu: true` 等

### 添加新节点

1. 在 `node-hub/` 创建新节点目录
2. 编写 `node.yaml` 和 `run.py`
3. 在 `planning_simulation.yaml` 中添加节点定义和边
4. 按拓扑顺序定义依赖关系

### 调试模式

启用调试输出：
```bash
# 启用详细日志
python3 -m runtime.main examples/planning_simulation.yaml --log-level DEBUG

# 启用仿真器状态
# 编辑 planning_simulation.yaml，修改:
#   sim_output:
#     enable_state: true
```

## 输出和结果

### 日志文件

- `logs/nodeflow.log`: 运行时日志
- `logs/nodeflow_errors.log`: 错误日志
- `logs/planning_simulation.jsonl`: 结构化数据日志（如启用）

### 可视化结果

- `logs/jpg/*.jpg`: 轨迹对比图像
  - 蓝色线：规划路径
  - 红色线：实际轨迹
  - 绿色区域：地块边界

### 性能分析

查看运行时统计：
```bash
# 查看节点启动时间
grep "started successfully" logs/nodeflow.log

# 查看数据流速率
grep -E "rtk_fix|velocity_cmd" logs/nodeflow.log | head -20

# 计算往返延迟
tail -100 logs/nodeflow.log | grep -E "timestamp"
```

## 参考资源

- **配置文件**: `examples/planning_simulation.yaml`
- **仿真器文档**: `simulator/README.md`
- **测试脚本**: `tests/e2e_test_planning_simulation.py`
- **运行时文档**: `docs/NODE_TESTING_GUIDE.md`
- **节点实现**:
  - `node-hub/sim_output/run.py`
  - `node-hub/global_coverage/run.py`
  - `node-hub/velocity_controller/run.py`
  - `node-hub/sim_input/run.py`
  - `node-hub/trajectory_viz/run.py`

---

**最后更新**: 2025-12-25
**测试框架版本**: v1.0
**状态**: 已验证可用 ✓
