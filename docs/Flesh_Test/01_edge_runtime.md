# 模块审阅报告：edge/runtime（运行时框架核心）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 本报告按全仓 v1 范围定级。按上机边界重新评定后：P0-1（日志句柄泄漏）降为**量产前 P1**（重启策略限制短期泄漏，长期反复崩溃才显现）；P0-2（监控线程无保护）保持，列**无人值守前门禁**；P1-1/2/3 在 Linux 单实例样机上不构成上机阻断。详细映射见汇总报告第零节。

## 1. 模块职责

配置驱动的节点编排运行时：YAML 解析 → 图拓扑分析 → 节点进程启动 → 数据流运行 → 崩溃监控重启 → 优雅关闭。支持单次运行（`run()`）、多轮循环（`run_with_loop()`）、守护进程（`run_as_daemon()`，通过 `runtime.control` 缓冲命令协议驱动）。

| 子模块 | 文件 | 行数 | 职责 |
|---|---|---|---|
| 入口 | `main.py` | 892 | 生命周期主类 `NodeFlowRuntime`、信号处理、daemon 命令协议 |
| config | `models.py` / `validator.py` / `yaml_parser.py` | 113/114/206 | YAML 解析、配置结构、校验 |
| graph | `topology.py` / `validator.py` | 183/136 | Kahn 分层拓扑排序、循环依赖检测、图校验 |
| orchestrator | `env_builder.py` / `node_launcher.py` / `startup_coordinator.py` | 72/434/241 | 环境变量构建、subprocess 生命周期、分层启动 |
| monitoring | `node_monitor.py` / `restart_policy.py` | 255/122 | 崩溃监控、指数退避重启 |
| utils | `constants.py` / `errors.py` / `logger.py` | 4/116/70 | 路径常量、异常体系、stderr 日志 |
| node_hub | `node_registry.py` / `scanner.py` | 159/103 | 节点包扫描、manifest 注册 |

**合计 16 个文件，3,220 行。**

## 2. 核心流程

- **启动链路**: `main()` → `_initialize_framework()`（YAML → ConfigValidator → NodeRegistry 扫描 → GraphValidator → TopologyAnalyzer 分层）→ `start_dataflow()`（清 buffer → NodeLauncher + StartupCoordinator 分层启动 → NodeMonitor 挂重启回调 → 写 PID）。
- **运行链路**: 主循环 1s 轮询 duration / 外部 shutdown；daemon 模式轮询 `runtime.control` 缓冲执行 start/stop/shutdown 并回写 `runtime.status`。
- **关闭链路**: SIGTERM/SIGINT → `stop_dataflow()`（monitor join(5s) → 反向 SIGTERM→wait→SIGKILL 进程组）→ atexit 屏蔽。
- **崩溃恢复**: monitor 每秒 `poll()`，崩溃后 RetryTracker 指数退避调度重启；稳定 300s 重置计数。

## 3. 发现的问题

### P0（核心路径确定性缺陷）

| # | 位置 | 问题 |
|---|---|---|
| P0-1 | `orchestrator/node_launcher.py:113-130,398-424` | **崩溃重启循环中日志 handler 永久泄漏 + FD 累积**：RotatingFileHandler 在去重检查前创建（文件句柄立即打开）；崩溃路径 `node_monitor.py:129-141` 从不调用 `close_node_logs`；重启时因 baseFilename 相同不挂接新 handler 且新 handler 被丢弃不 close。每次"崩溃→重启"确定泄漏 FD，数百次后超 ulimit 导致 Popen 失败。 |
| P0-2 | `monitoring/node_monitor.py:80-114` | **监控线程无异常保护**：`_monitor_loop` 整体无 try/except；`process.communicate(timeout=0.1)` 与 launcher 转发线程并发读同一管道，异常时监控线程静默死亡，此后无节点重启、无告警。 |

### P1（功能失效 / 竞态 / 资源风险）

| # | 位置 | 问题 |
|---|---|---|
| P1-1 | `main.py:46,877`; `utils/logger.py:11` | **--log-level 参数完全失效**（已验证）：`self.log_level` 存储后从未使用，`setup_logger` 模块导入时以默认 INFO 创建且 handlers 非空即返回。 |
| P1-2 | `node_launcher.py:50,228`; `startup_coordinator.py:147`; `node_registry.py:108` | **平台硬编码 "linux"**：所有 `launch()` 调用不传 platform，恒按 linux 键查找 entrypoint；声明了 darwin/macos entrypoint 的节点在 macOS 上必然启动失败。 |
| P1-3 | `node_launcher.py:12` | **顶层 `import fcntl` 使 Windows 完全不可用**（模块导入即崩），与代码内 `sys.platform != "win32"` 分支自相矛盾。 |
| P1-4 | `main.py:455-465`; `node_monitor.py:71-77,184-188` | **停机期间监控线程重启竞态 → 孤儿进程**：`stop_dataflow` join 仅 5s，若监控线程正处于 `_execute_restart` 中，新进程在 `self.processes={}` 之后写回共享 dict，永不终止。 |
| P1-5 | `main.py:86-107` vs `478-494` | **信号在初始化窗口被吞掉**：`_signal_handler` 仅在 running/dataflow_running 时置位；初始化期间（含节点库扫描）到达的 SIGTERM/SIGINT 被忽略，关机请求丢失。 |
| P1-6 | `node_launcher.py:113-118` | 日志轮转上限 1GB × 30 备份 × 双流 = 每节点约 62GB，硬编码无配置入口。 |
| P1-7 | `node_launcher.py:287-302` | 节点退出时 `readlines()` 全量读入可达 1GB 的日志文件再取末 5 行，易 OOM。 |
| P1-8 | `main.py:190-214,371-372` | daemon 模式 `_clean_buffers` 清空自身正在使用的 control/status 缓冲，命令/状态通道瞬时失效。 |
| P1-9 | `main.py:172-179`; `utils/constants.py` | `_emergency_cleanup` 对全局共享 `/tmp/nodeflow/buffers` 无条件 rmtree，多实例并存时破坏他方数据；PID 文件 `/tmp/nodeflow_runtime.pid` 亦为全局硬编码。 |

### P2（次要问题摘选）

- `restart_policy.py:30-56`：`max_retries=3` 实际只允许 2 次重启（off-by-one，已验证 `can_retry` 用 `<`）。
- `node_monitor.py:190-191`：重启回调失败仅记日志不重新调度，剩余重试次数浪费。
- `node_monitor.py:247-253`：`get_all_status` 迭代与监控线程写 `self.processes` 无锁 → 可能 `RuntimeError`。
- `graph/topology.py:49`：对不存在的 `to_node` 直接 `graph[to_node]` KeyError（类本身不健壮）。
- `config/yaml_parser.py:59`：`params: null` 时 `NodeInstance.params=None`，daemon 注入 `params.update` AttributeError。
- `env_builder.py:39-54`：输入端口忽略输入侧 buffer_size/conflate 声明。
- `env_builder.py:32`：`project_root = node_hub_path/../..` 硬编码目录层级假设。
- `main.py:509-513`：`run()` 中 `SharedBufferLite("control.shutdown_request")` 从不 close（mmap+FD 泄漏）。
- 大量异常类（SocketError/ProtocolError/TypeMismatchError 等）从未被使用（死代码）。
- `node_launcher.py:151-173`：转发线程 50ms 忙轮询空转。

## 4. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C7: main.py 中 `setLevel` 调用次数 = 0，log_level 存储后未使用 | **确认（P1-1）** |
| C8: `node_launcher.py:50` `platform: str = "linux"` 默认值，调用点均不传参 | **确认（P1-2）** |
| C9: pytest 收集 443 项，tests/mcp、tests/legacy 按 norecursedirs 排除 | 符合当前配置 |

## 5. 总体评价

**优点**: 分层启动（Kahn 拓扑 + 层间串行）与纯 mmap SharedBuffer IPC 设计简洁一致；进程组终止策略（start_new_session + SIGTERM→wait→SIGKILL 降级链）实现细致；`_switch_task_preset` 路径穿越防护正确；stderr 日志与 CLI stdout 协议隔离是正确工程决策。

**主要风险**: ① 崩溃重启路径的日志 handler 生命周期管理（P0-1）与监控线程裸奔（P0-2）直接威胁长时运行可靠性；② "宣称支持但实际失效"的配置（log-level、platform、Windows）；③ 进程生命周期竞态（停机重启孤儿进程、信号漏关窗口）。

**建议优先修复**: P0-1（handler 去重前先关闭旧 handler、`_handle_node_crash` 中调用 close_node_logs）、P0-2（`_monitor_loop` 整体 try/except + 告警）、P1-2（按 `sys.platform` 映射 platform 参数）。
