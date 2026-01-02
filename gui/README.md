# NodeFlow Runtime 控制面板

简单的图形界面，用于管理 NodeFlow 数据流。

## 快速启动

```bash
# 从项目根目录
./start_gui.sh

# 或从 gui 目录
cd gui
./start_gui.sh
```

## 功能特性

- ✅ 选择 examples 目录中的配置文件
- ✅ 一键启动/停止 Runtime（后台守护进程模式）
- ✅ 启动/停止/重启数据流（无需重启 Runtime）
- ✅ 实时状态监控（PID、运行时间）
- ✅ 彩色日志输出（错误红色、成功绿色、警告橙色）
- ✅ 查看 Runtime 详细日志

## 界面预览

```
┌─────────────────────────────────────────────────────────────┐
│ NodeFlow Runtime Control Panel                               │
├─────────────────────────────────────────────────────────────┤
│ 配置文件选择                                                  │
│   数据流配置: [planning_simulation.yaml ▼]  [刷新]          │
├─────────────────────────────────────────────────────────────┤
│ 控制面板                                                      │
│   Runtime:  [▶ 启动 Runtime]  [⏹ 停止 Runtime]              │
│   数据流:   [▶ 启动数据流]    [⏹ 停止数据流]  [🔄 重启]      │
├─────────────────────────────────────────────────────────────┤
│ 运行状态                                                      │
│   ● Runtime: 运行中 (PID: 12345, 运行时间: 2.5h)              │
├─────────────────────────────────────────────────────────────┤
│ 日志输出                                                      │
│   [时间戳] 日志内容...                                        │
│   [清除日志]  [查看 Runtime 日志]                            │
└─────────────────────────────────────────────────────────────┘
```

## 文件说明

- `gui_runtime_control.py` - GUI 主程序
- `start_gui.sh` - 启动脚本（从 gui 目录运行）
- `GUI_USER_GUIDE.md` - 详细使用指南
- `README.md` - 本文件（快速参考）

## 等价 CLI 命令

| GUI 操作 | CLI 命令 |
|----------|---------|
| ▶ 启动 Runtime | `python3 -m tools.cli.core.cli runtime start <config> --background` |
| ⏹ 停止 Runtime | `python3 -m tools.cli.core.cli runtime stop` |
| ▶ 启动数据流 | `python3 -m tools.cli.core.cli runtime start-dataflow` |
| ⏹ 停止数据流 | `python3 -m tools.cli.core.cli runtime stop-dataflow` |
| 🔄 重启数据流 | `python3 -m tools.cli.core.cli runtime restart-dataflow` |

## 系统要求

- Python 3.8+
- tkinter（Python 标准库，通常已预装）
- macOS / Linux

## 故障排查

### GUI 无法启动

```bash
# 检查 Python 版本
python3 --version

# 检查 tkinter
python3 -c "import tkinter; print('OK')"

# 检查语法
cd gui
python3 -m py_compile gui_runtime_control.py
```

### Runtime 启动失败

1. 点击 **"查看 Runtime 日志"** 按钮查看错误
2. 检查配置文件是否正确
3. 确认仿真器是否运行（如需要）

### 按钮状态不更新

- GUI 每 2 秒自动更新状态
- 关闭后重新打开 GUI
- 使用 CLI 命令手动检查：`python3 -m tools.cli.core.cli runtime status`

## 相关文档

- [GUI_USER_GUIDE.md](GUI_USER_GUIDE.md) - 详细使用指南
- [../DAEMON_MODE_GUIDE.md](../DAEMON_MODE_GUIDE.md) - 守护进程模式说明
- [../docs/README.md](../docs/README.md) - 项目文档索引

---

**版本**: 1.0
**更新日期**: 2025-12-29
