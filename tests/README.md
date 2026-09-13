# NodeFlow 测试说明

仓库级 pytest 配置在 [pytest.ini](../pytest.ini)，权威入口是 [tools/run_tests.sh](../tools/run_tests.sh)。不要通过遍历所有 `test_*.py` 并逐个直接执行来替代 pytest 收集。

## 快速命令

从仓库根目录运行：

```bash
python -m pip install -r requirements.txt
python -m pip install -r cloud/server/requirements.txt

./tools/run_tests.sh collect
./tools/run_tests.sh quick
./tools/run_tests.sh full
./tools/run_tests.sh preflight
```

| 模式 | 实际范围 |
|---|---|
| `collect` | 使用 `pytest.ini` 执行 `pytest --collect-only` |
| `quick` | `tests/unit` + `cloud/server/tests`；当前 CI 使用此模式 |
| `full` | `pytest.ini` 的全部默认收集范围 |
| `preflight` | `python3 -m tools.preflight_runtime`，检查本地运行前提 |

## 默认收集范围

`pytest.ini` 当前包含：

- `tests/unit/`：Runtime、SDK/IPC、CLI、协议、任务资产和关键节点逻辑；
- `tests/integration/`：编排、端口、规划控制闭环、日志与可视化集成；
- `tests/smoke/`：Runtime 预检；
- `cloud/server/tests/`：Cloud API、规划、调度、坐标系和文件；
- `edge/nodes/`：节点目录内符合 pytest 规则的测试。

当前默认排除：

- `tests/legacy/` 和 `tests/mcp/`；
- `simulation/` 独立测试；
- `tools/editor/`、`tools/cli/` 下的自带测试；
- 文档、脚本、配置、前端构建产物等目录。

`tests/` 根目录中遗留的独立测试文件也不属于当前 `testpaths`。需要它们时应明确指定文件，并先判断其路径和假设是否仍适用。

## CI 范围

[GitHub Actions](../.github/workflows/test.yml) 在以下矩阵运行：

- Ubuntu latest / macOS latest；
- Python 3.12；
- 安装根依赖和 Cloud server 依赖；
- 先收集 `tests/unit`，再执行 `./tools/run_tests.sh quick`。

因此 CI 通过只表示 unit 与 Cloud server 快速集通过，不代表以下内容已验证：

- 完整 integration/smoke；
- 仿真服务端到端测试；
- MQTT broker 与真实 Edge Agent 链路；
- Web 前端 TypeScript 构建；
- 串口、PWM、网络 RTK 和真实执行器；
- MCP 或 Tk GUI。

## 按子系统运行

```bash
# 单个测试文件或测试函数
python -m pytest -q tests/unit/test_node_monitor.py
python -m pytest -q tests/unit/test_node_monitor.py::test_name

# 集成与 smoke
python -m pytest -q tests/integration
python -m pytest -q tests/smoke

# Cloud
python -m pytest -q cloud/server/tests

# 带 preflight marker 的 pytest 测试
python -m pytest -q -m preflight
```

仿真器有独立脚本：

```bash
cd simulation/tests
./run_tests.sh
```

该脚本会处理本机 5555 端口并启动/停止仿真服务，可能影响正在运行的仿真实例。先确认端口没有承载其他工作。

前端至少应执行构建：

```bash
cd cloud/web && npm install && npm run build
cd tools/editor/web-editor && npm install && npm run build
cd cloud/monitor && npm install && npm run build
```

## 添加测试

- 纯逻辑与故障边界放在 `tests/unit/`；
- 多模块、子进程或真实 IPC 放在 `tests/integration/`；
- 运行环境最小可用性放在 `tests/smoke/`，需要时标记 `@pytest.mark.preflight`；
- Cloud API/服务测试放在 `cloud/server/tests/`；
- 需要独立服务和端口管理的仿真测试留在 `simulation/tests/`。

新测试必须能被 `./tools/run_tests.sh collect` 正确收集。涉及时间、随机数、进程和网络端口时，应设置确定性输入、明确超时，并在失败路径清理资源。

文档不记录固定的“已通过 N 项”数字；提交时的真实状态应由 CI 或对应命令输出证明。
