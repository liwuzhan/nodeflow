# NodeFlow Runtime 控制面板

`tools/gui/` 提供基于 tkinter 的本机 Runtime 控制界面，是 `nodeflow-cli runtime ...` 的轻量图形封装。

## 启动

从仓库根目录：

```bash
tools/gui/start_gui.sh
```

或：

```bash
python3 tools/gui/gui_runtime_control.py
```

要求 Python 3.12+ 和 tkinter。无桌面环境、脚本化运维和远程排障应优先使用 CLI。

## 功能

- 从仓库 `examples/` 选择 Runtime YAML；
- 后台启动/停止 Runtime Daemon；
- 启动、停止和重启数据流；
- 查看 PID、运行时间和控制操作日志；
- 打开 Runtime 后台日志。

| GUI 操作 | 等价命令 |
|---|---|
| 启动 Runtime | `nodeflow-cli runtime start <config> --background` |
| 停止 Runtime | `nodeflow-cli runtime stop` |
| 启动数据流 | `nodeflow-cli runtime start-dataflow` |
| 停止数据流 | `nodeflow-cli runtime stop-dataflow` |
| 重启数据流 | `nodeflow-cli runtime restart-dataflow` |

Runtime 后台日志默认在 `/tmp/nodeflow_runtime.log`，节点结构化日志默认在 `/tmp/nodeflow/logs/`。

详细界面说明见 [GUI_USER_GUIDE.md](GUI_USER_GUIDE.md)。其中若出现开发者机器的绝对路径或旧示例文件，以本页和仓库当前目录为准。

系统级工具说明见 [仿真、CLI 与开发工具](../../docs/SIMULATION_AND_TOOLS.md)。
