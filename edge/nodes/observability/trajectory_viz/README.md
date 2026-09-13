# 轨迹与三维作业观察节点

`observability/trajectory_viz` 接收任务、规划路线、定位和机具状态，提供二维轨迹与三维农场画面。它既可观察仿真，也可接收实车遥测；页面只读，不下发车辆指令。

## 启动

从仓库根目录安装本节点依赖：

```bash
python3 -m pip install -r edge/nodes/observability/trajectory_viz/requirements.txt
```

启动完整规划仿真，在两个终端分别运行：

```bash
# 终端 1
python3 simulation/server.py
```

```bash
# 终端 2
python3 -m edge.runtime.main configs/graphs/planning_simulation.yaml
```

- `http://localhost:8080/3d`：三维观察、真值与估计叠加、前瞻点、覆盖与回放。
- `http://localhost:8080/`：原二维轨迹、统计与曲线。

三维页面的 Three.js r180 和 GLB 模型随仓库提供，运行时不需要访问外部资源网站。二维页面继续使用原 Plotly / SocketIO 实现。

## 在运行图中配置

下面是节点实例片段；完整连线见根目录 [仿真图](../../../../configs/graphs/planning_simulation.yaml) 和 [实车图](../../../../configs/graphs/planning_with_real_rtk.yaml)。

```yaml
nodes:
  - id: trajectory_viz
    package: observability/trajectory_viz
    params:
      web_host: "127.0.0.1"
      web_port: 8080
      frame_interval_s: 0.1
      scene_interval_s: 1.0
      stale_after_s: 1.0
      update_interval: 5.0
      replay_sample_interval: 0.2
      max_replay_samples: 3000
      timeout: 0.0
```

节点默认绑定 `127.0.0.1`。预置仿真图使用 `0.0.0.0` 供局域网观察，预置实车图沿用本机地址；需要远程观察时调整实际运行图的 `web_host`。

## 输入与来源

| 输入端口 | 类型 | 用途 |
|---|---|---|
| `task_enu` | `planning.task_enu` | 地块外边界、孔洞、任务与机具尺寸 |
| `global_path` | `planning.path` | 兼容路径输入 |
| `operation_plan` | `planning.operation_plan` | 带作业段语义的路径，优先于普通路径 |
| `pose_enu` | `localization.pose_enu` | 定位链路位姿；实车主位置，仿真对照位置 |
| `state_info` | `json` | 可选仿真真值，必须与路径处于同一任务坐标 |
| `raw_rtk` | `sensor.rtk` | 可选 RTK 质量、航向有效性与来源诊断 |
| `next_point` | `planning.waypoint` | 前瞻点与目标状态 |
| `velocity_cmd` | `control.velocity` | 速度指令和跟踪方法，非实测速度 |
| `path_progress` | `planning.path_progress` | 原二维复盘的路径进度和段状态 |
| `implement_state` | `implement.state` | 可选实际机具反馈 |
| `tillage_status` | `implement.tillage_status` | 可选控制器逻辑状态，显示为估计 |
| `tillage_cmd` | `implement.tillage_cmd` | 兼容原指令复盘，不据此驱动三维实际升降 |

`state_info`、`raw_rtk`、`implement_state`、`tillage_status`、`tillage_cmd` 仅在运行图连接后创建对应输入端口。

机具显示的优先级为仿真真值、实际反馈、控制器逻辑状态。逻辑状态输出 `source: controller_status`、`estimated: true`；即便 `ready_source` 是 `feedback`，它仍然不是实测悬挂高度。三维升降只使用未过期的真值或实际反馈，其他情况下淡化机具并说明未接实测。

实车覆盖仍由原采样链路按定位和机具控制状态估算，显示“机具按控制状态估算”，不能当成实际农艺完成的验证。新 `implement_state` 直连用于显示帧、升降动画和本段回放地面重建，没有改写实时累计覆盖计算。

没有连接真值时，实车画面只显示定位估计。连接了真值但尚未收到有效包时，主车辆等待真值。缺失或无效的航向不会被默认朝向替代。

输出端口 `web_url` 的类型为 `json`，包含页面根地址、更新时间、场景更新次数和指标；三维入口是在该根地址后添加 `/3d`。

## 刷新、失联与回放

| 参数 | 默认值 | 说明 |
|---|---|---|
| `web_host` | `127.0.0.1` | 监听地址 |
| `web_port` | `8080` | 监听端口 |
| `frame_interval_s` | `0.1` 秒 | 姿态与状态小包刷新 |
| `scene_interval_s` | `1.0` 秒 | 场景、路径与累计覆盖刷新 |
| `stale_after_s` | `1.0` 秒 | 本地有效收包年龄超过此值标为过期 |
| `update_interval` | `5.0` 秒 | 仅日志节流 |
| `replay_sample_interval` | `0.2` 秒 | 有新主姿态时的回放记录间隔 |
| `max_replay_samples` | `3000` | 默认约 10 分钟连续数据，保存在内存 |
| `timeout` | `300.0` 秒 | manifest 默认运行时长；设为 `0` 持续运行 |
| `implement_length_m` | `0.2` 米 | 原覆盖评价的机具长度默认值，可由任务覆盖 |
| `implement_offset_m` | `0.0` 米 | 原覆盖评价的纵向偏置默认值，车前为正 |

收包年龄使用本地单调时钟。断流后继续报告年龄，车辆冻结在最后有效位置；浏览器与观察服务失联时显示中断，不按旧速度指令继续推算。

未处理地面使用浅色干土，已处理地面使用深棕细纹；可另外打开覆盖分析着色。回放保存真值、估计和状态，进入时复用机具扫掠算法重建本段记录的地面，提供暂停、拖动与倍速。断档、过期、抬升或停转不连接扫掠。回放地面只代表保留记录内的作业，整场累计覆盖率继续隐藏。新任务清除旧场景和回放，节点退出后内存记录消失；当前没有文件导入导出。

## 页面接口与代码

| 接口 | 内容 |
|---|---|
| `GET /api/monitor/frame` | 最新姿态与状态，小包；首帧前为 `null` |
| `GET /api/monitor/scene?since=<revision>` | 地块、孔洞、路径与覆盖；版本不变时只返回版本提示 |
| `GET /api/monitor/replay` | 当前内存记录，`frames` 数组；`?ground=1` 增加按原帧索引排列的本段扫掠多边形 |

三维页面分别轮询小包和场景。这些新增接口只读；回放暂停不会停止车辆。

- `run.py`：输入接收、任务缓存、刷新与记录节拍。
- `monitor.py`：显示帧、来源标记与年龄适配。
- `atom.py`：原轨迹指标、评价采样与覆盖整理。
- `replay_ground.py`：复用机具扫掠算法，生成本段回放的地面处理增量。
- `web_server.py`：二维页面、三维入口、静态资源和数据接口。
- `static/3d/`：三维场景与交互；`static/vendor/three/` 为本地绘制依赖。

三维模型是长 1.6 米、宽 1.2 米的外观示意，不改变图中作业幅宽。当前运动计算仍以平面运动为主；原始 RTK 元数据已可读取，但三维原始观测点、独立航向箭头尚未绘制。曲线仍在二维页面。完整范围见 [轻量三维农场观察窗口](../../../../docs/LIGHTWEIGHT_3D_SIMULATION.md)。

## 排查入口

页面打不开时检查观察节点日志、`web_host` 和 8080 端口。三维加载失败时检查浏览器图形加速及本地静态资源请求，也可先打开二维入口。显示“等待数据”时检查输入连线；显示“数据过期”时查看相应来源与收包年龄，而不是提高日志频率。

本轮完成了仿真与观察数据链路验证，尚未完成实车监控验证。
