# 仿真、CLI 与开发工具

NodeFlow 的核心运行不依赖 Web 界面或 MCP。本页说明仿真服务、主要 CLI，以及各辅助工具目前承担的职责。

## 1. 农田仿真服务

`simulation/` 是一个独立进程，通过 ZMQ REQ/REP 在默认端口 5555 提供 2D 车辆、地块和传感器模拟。

主要模块：

| 文件 | 职责 |
|---|---|
| `server.py` | ZMQ 服务、请求分派、仿真循环和配置加载 |
| `physics.py` | 运动学、加速度限制、打滑与地形扰动 |
| `sensors.py` | GPS、RTK、IMU 和里程计 |
| `state.py` | 车辆当前状态与有限历史 |
| `field_generator.py` | 矩形/不规则地块、障碍物和孔洞 |
| `evaluation.py` | 实际机具扫掠、累计唯一覆盖/遗漏/重复面积 |
| `rtk_experiment.py` | 复用真实节点算法的固定时间步直线实验 |
| `config.yaml` | 当前默认地块、车辆、噪声、传感器与服务配置 |
| `example_usage.py` | 协议调用示例 |

当前默认配置使用：

- 10 ms 物理步长，即 100 Hz 内部仿真；
- 50 Hz RTK 固定采样，查询只读缓存；
- 可复现的随机种子；
- 100 m × 200 m 矩形地块，默认不生成孔洞；
- 线速度打滑与角速度地形扰动；
- 接近地块入口的初始车位；
- WGS84 参考点 `lon=121.5, lat=31.2`。

这些是当前 `simulation/config.yaml` 的开发默认值，不是固定协议。

新实现的可重复时序、定位/航向噪声、延迟、车辆响应与机具反馈门控，见 [仿真闭环与纯 RTK 复现实验](SIMULATION_RTK_EXPERIMENTS.md)。

### 启动

从仓库根目录：

```bash
python3 simulation/server.py

# 指定配置、端口或步长
python3 simulation/server.py --config path/to/config.yaml --port 5556 --dt 0.02
```

可用 `--no-realtime` 关闭服务端节流，但它不会同步加速独立节点；多进程图保持实时模式，确定性对照使用 `python3 -m simulation.rtk_experiment`。NodeFlow 图通过两个桥接节点接入：

- `sensing/sim_output`：读取地块、传感器和状态；
- `io/sim_input`：写入速度或电机命令。

### ZMQ 请求

请求与响应使用 JSON。

| `type` | 关键字段 | 行为 |
|---|---|---|
| `get_field` | 无 | 获取当前地块、孔洞、入口和版本 |
| `get_sensor` | `sensor=gps|rtk_gps|imu|odometry` | 获取传感器样本 |
| `set_actuator` | `actuator=velocity|motor`, `data` | 写速度或油门/转向命令 |
| `get_state` | 无 | 获取车辆和仿真状态 |
| `reset` | 无 | 重置车辆状态和仿真时钟 |

示例：

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

进一步说明见 [simulation/README.md](../simulation/README.md) 和 [simulation/docs](../simulation/docs/README.md)。

## 2. CLI

安装包后使用 `nodeflow-cli`；源码方式使用 `python3 -m tools.cli.core.cli`。虽然解析器内部仍以 `nodeflow` 显示命令名，实际 console entry point 是 `nodeflow-cli`。

| 命令 | 主要用途 |
|---|---|
| `node list/info` | 扫描 Node Hub、查看 manifest |
| `buffer list/inspect/read` | 查看 mmap 文件、头部和当前 payload |
| `health check/status/flow` | Schema、节点心跳和整图数据活性 |
| `runtime start/stop/status` | 管理 Runtime 进程 |
| `runtime start-dataflow/stop-dataflow/restart-dataflow` | 管理 Daemon 中的数据流轮次 |
| `status` | 聚合 PID、图、health、输出端口、问题和最近事故 |
| `logs` | 聚合/过滤/跟随结构化日志 |
| `monitor` | 定时显示 buffer 序列和内容摘要 |
| `simulator refresh` | 请求仿真器重新生成地块并重置 |
| `task run/list/show/cancel` | 本地任务文件和任务状态管理 |

CLI 会在 Runtime 运行时从 PID JSON 获取当前 run 的 buffer 目录。直接指定 `buffer list --dir` 或 `health flow --dir` 时，应确认传入的是当前 run 目录，而不是只看旧的固定默认目录。

实用命令：

```bash
nodeflow-cli --help
nodeflow-cli node info planning/global_coverage
nodeflow-cli status --json
nodeflow-cli logs --node track_controller --level WARNING --since "5m ago"
nodeflow-cli monitor --help
nodeflow-cli task run configs/graphs/tillage_task.yaml
```

## 3. Web Blueprint Editor

`tools/editor/web-editor/` 是 Vue 3 + TypeScript + Vue Flow 编辑器。当前源码包含：

- 节点库浏览、搜索和 manifest 加载；
- 拖拽画布、端口连接、类型检查和图验证；
- 参数编辑、分组和注释；
- YAML 导出/保存；
- 项目 JSON 导入导出；
- Runtime 配置选择、启动/停止、数据流控制和日志视图。

后端路由已经合入 `cloud/server/routers/editor.py`，挂载在 `/editor/api/*`。开发时可以显式指定 API 基址，避免依赖前端仓库内可能变化的代理设置：

```bash
# 终端 1，仓库根目录
python3 -m uvicorn cloud.server.app:app --host 127.0.0.1 --port 8080

# 终端 2
cd tools/editor/web-editor
npm install
VITE_API_BASE_URL=http://localhost:8080/editor/api npm run dev
```

编辑器是配置生产和运维辅助界面。导出的 YAML 仍应经过 Runtime 验证、测试和实机参数审查，不能把画布连线成功视为 payload 语义正确。

## 4. Tk Runtime GUI

`tools/gui/` 提供轻量本机控制面板，封装 Daemon 模式的 CLI 操作：

```bash
tools/gui/start_gui.sh
```

它依赖 Python 的 tkinter，适合本机开发和演示。CLI 是脚本化、远程排障和无桌面环境下的首选入口。

## 5. Cloud Web 与 Monitor

- `cloud/web/` 是主要农场管理前端，访问 `/api/v1`。
- `cloud/monitor/` 是保留的只读监工界面，显示车辆、地块和 SSE 状态；它没有替代主前端，启用前应复核其开发代理和当前 Cloud 端口。

两者都不是 Edge Runtime 的依赖。Cloud 启动方式见 [云边任务系统](CLOUD_EDGE_TASKS.md)。

## 6. MCP

`tools/mcp/mcp_server.py` 包含 9 个面向 AI 调试的工具定义：

- `nodeflow/get-node-info`
- `nodeflow/validate-yaml`
- `nodeflow/edit-yaml`
- `nodeflow/run-runtime`
- `nodeflow/stop-runtime`
- `nodeflow/read-logs`
- `nodeflow/get-runtime-status`
- `nodeflow/buffer-read`
- `nodeflow/node-health`

MCP 属于实验性开发工具，不在 Edge Runtime 或默认 CI 主路径内。仓库经历过目录整合，启用前应单独验证 MCP SDK 版本、项目根路径、Runtime manager 导入和所有写操作的路径边界。不要把 MCP 可用性作为现场运行的前提。

## 7. 测试工具

仓库级入口：

```bash
./tools/run_tests.sh collect
./tools/run_tests.sh quick
./tools/run_tests.sh full
./tools/run_tests.sh preflight
```

仿真子系统还有独立测试脚本，但其中会启动服务并处理 5555 端口，运行前应确认不会中断正在使用的仿真实例。完整范围见 [测试说明](../tests/README.md)。

前端分别使用自己的 `package.json`：

```bash
cd cloud/web && npm run build
cd tools/editor/web-editor && npm run build
cd cloud/monitor && npm run build
```

不要用“仓库存在前端代码”替代实际的 TypeScript 构建和后端联调结果。
