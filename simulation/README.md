# NodeFlow 农田仿真器

`simulation/` 是独立的农田机器人仿真服务，运动计算以平面为主。它模拟地块、差速/履带车辆运动、打滑与地形扰动，以及 GPS、RTK、IMU 和里程计；NodeFlow 通过 `sensing/sim_output` 与 `io/sim_input` 两个节点桥接，观察节点提供二维和三维画面。

纯 RTK 直线摆动的对照实验、覆盖评价及本轮修改见 [仿真闭环与纯 RTK 复现实验](../docs/SIMULATION_RTK_EXPERIMENTS.md)。

大半径隔行回转、现成螺旋候选和整田跟踪实验见 [连续旋耕规划器](../docs/CONTINUOUS_TILLAGE_PLANNERS.md)。

三维观察窗口已接入车辆、机具、田界孔洞、路径、覆盖与回放，见 [轻量三维农场显示](../docs/LIGHTWEIGHT_3D_SIMULATION.md)。同一页面可接实车遥测，显示模型不改变运动与覆盖计算。

## 目录

```text
simulation/
├── server.py              # ZMQ REQ/REP 服务与仿真循环
├── physics.py             # 运动学、打滑和地形噪声
├── sensors.py             # GPS / RTK / IMU / odometry
├── state.py               # 车辆状态与有限历史
├── field_generator.py     # 地块、障碍物与孔洞生成
├── evaluation.py          # 机具扫掠与累计覆盖评价
├── rtk_experiment.py      # 复用节点算法的直线闭环实验
├── experiments/           # 无扰动、噪声、延迟与响应滞后对照
├── assets/tracked_tiller/  # 简化车辆/机具 GLB 与生成脚本
├── config.yaml            # 当前默认参数
├── example_usage.py       # 客户端示例
├── docs/                  # 详细协议和专题说明
├── tests/                 # 独立仿真测试
└── utils/                 # 坐标和随机地块工具
```

## 启动

从仓库根目录：

```bash
python3 simulation/server.py

# 可选
python3 simulation/server.py --config path/to/config.yaml
python3 simulation/server.py --port 5556 --dt 0.02
python3 simulation/server.py --no-realtime
```

服务默认监听 ZMQ 5555。当前 `config.yaml` 使用 10 ms 物理步长和 50 Hz RTK；配置文件中的值优先于文档示例。

无界面、可重复实验：

```bash
python3 -m pip install -r simulation/requirements.txt
python3 -m simulation.rtk_experiment --output /tmp/nodeflow-rtk-experiment
```

多进程闭环保持实时模式。`--no-realtime` 不会同步加速其他节点；固定时间步实验使用上述单进程入口。

启动 NodeFlow 规划闭环：

```bash
# 终端 1
python3 simulation/server.py

# 终端 2，仓库根目录
python3 -m edge.runtime.main configs/graphs/planning_simulation.yaml
```

打开 `http://localhost:8080/3d` 查看三维画面，`http://localhost:8080/` 保留二维轨迹和曲线。三维绘制依赖与模型随仓库提供，不需要外部资源网站；浏览器需要图形加速。

## 三维观察与监控

实体车辆使用 `state_info` 仿真真值，半透明车辆使用控制链路的定位估计，两者都在任务坐标内。机具真值或直接 `implement_state` 反馈驱动升降；`tillage_status` 仅作为控制器逻辑状态，明确标注估计，不据此假装实际升降。

姿态小包默认每 0.1 秒更新，路径和覆盖默认每 1 秒更新，`update_interval` 仅控制日志。超过 1 秒没有有效位姿，页面标为过期并冻结车辆；无有效航向不会补成默认朝向。

三维回放保存在观察节点内存，默认最多 3000 帧、每 0.2 秒记录新主位姿，约 10 分钟连续数据。回放期间隐藏当前累计覆盖；切换任务和进程退出都会清空记录。三维观察接口 `/api/monitor/frame`、`/api/monitor/scene`、`/api/monitor/replay` 均为只读 GET，页面暂停只作用于回放。

接入实车时不产生真值：车辆位置是定位估计，现有覆盖链路仍按定位和机具控制状态估算，不能视为实际农艺完成的验证。新直接机具反馈目前用于显示帧和升降动画，没有改写原覆盖算法。原始 RTK 诊断元数据已可接入，但三维独立观测点与航向箭头尚未绘制；本轮没有实车验证。

## 仿真服务 API

以下是 ZMQ 仿真服务的请求，和上述只读观察接口分开；请求和响应使用 JSON：

| 请求 `type` | 行为 |
|---|---|
| `get_field` | 获取地块边界、孔洞、入口和版本 |
| `get_sensor` | 获取 `gps`、`rtk_gps`、`imu` 或 `odometry` |
| `set_actuator` | 写 `velocity`、`motor` 或 `implement` 控制 |
| `get_state` | 获取完整车辆/仿真状态 |
| `reset` | 保留当前地块，清除车辆、命令、机具、采样队列和历史 |

```json
{
  "type": "set_actuator",
  "actuator": "velocity",
  "data": {
    "linear_velocity": 1.0,
    "angular_velocity": 0.1
  }
}
```

更完整的字段说明见 [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md) 和 [docs/README.md](docs/README.md)。

## 测试

```bash
python3 -m pytest tests/unit/test_simulation_*.py -q
```

新回归在仓库 `tests/unit` 中。旧 `simulation/tests/run_tests.sh` 会占用并清理 5555 端口，不应与正在进行的仿真会话并行执行；默认 pytest 仍排除该历史目录。

## 边界

- 仿真器是功能和回归验证工具，不是精确的土壤、液压、履带接地或 GNSS 射频模型。
- 随机噪声、地块和初始位姿由配置与随机种子控制。
- 仿真成功不代表实机速度、转角、PWM、急停或机具时序已经安全标定。

系统级说明见 [仿真、CLI 与开发工具](../docs/SIMULATION_AND_TOOLS.md)。
