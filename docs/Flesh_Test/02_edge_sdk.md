# 模块审阅报告：edge/sdk（节点开发 SDK）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 按上机边界重新评定后：P1-1（InputPort 重启后无重连/seq 重同步）降为**量产前 P1**——首次正常启动不受影响，仅自动重启节点后可能断流，不阻止第一轮上机，无人值守运行前必须解决；P1-4（看门狗 ppid==1 误杀）在样机由 runtime 进程组拉起时不触发。详细映射见汇总报告第零节。

## 1. 模块职责

节点开发 SDK：节点生命周期入口（`NodeFlowSDK`）、纯 mmap 端口封装（`port.py`）、SharedBuffer 共享内存协议（`shared_buffer_lite.py`）、JSONL 结构化日志（`structured_logger.py`）、命令行参数解析（`param_parser.py`）。

| 文件 | 行数 | 职责 |
|---|---|---|
| `nodeflow_sdk.py` | 479 | 生命周期钩子（setup/loop/cleanup/run 由节点自编排）、env 解析、端口创建、健康心跳、父进程看门狗 |
| `port.py` | 257 | OutputPort（写）/ InputPort（轮询读）、schema 校验、late-joiner 快照 |
| `shared_buffer_lite.py` | 191 | mmap 核心：MsgPack 序列化、tombstone 写协议、header 比对读协议、进程内 RLock |
| `structured_logger.py` | 268 | JSONL 文件 + 控制台双输出、custom_fields |
| `param_parser.py` | 74 | `--params` JSON 解析 |

**合计 5 个有效文件，1,269 行。**

## 2. 核心实现

- **写协议（tombstone）**: `write()` 先置 length=0 并 flush（tombstone）→ 写数据区 → 写 seq+1 和 length → flush。序列号 uint32 回绕 `& 0xFFFFFFFF`。
- **读协议**: 通过文件 fd 读 8 字节 header（seq+length），读数据后再次比对 header——不一致则重试（最多 5 次），保证 latest-value 语义下无撕裂读。
- **recv_latest**: 无锁快读 seq → `diff=(cur-last)&0xFFFFFFFF` 判新（支持回绕）→ 二次校验后更新 last_sequence。
- **锁**: `_PROCESS_LOCKS` 为进程内 RLock（按 buffer path），跨进程写安全依赖"单写者"约定。
- **看门狗**: 1s 检查 ppid，父进程死亡即 atexit + os._exit(1)；健康心跳线程 2s 写 `{node_id}.health`。

## 3. 发现的问题

### P1（高）

| # | 位置 | 问题 |
|---|---|---|
| P1-1 | `port.py:210-213` | **InputPort 序列号陈旧 → 永久断流**：上游 buffer 被删除重建后 seq 归零，`0<diff<0x80000000` 恒为假，该端口永远读不到新数据且无再同步路径。 |
| P1-2 | `port.py:164-180` + `shared_buffer_lite.py:59-62` | **InputPort 连接竞态可致启动崩溃**：`buffer_path.exists()` 通过后文件可能仍为 0 字节 → `mmap(fd, 0)` 抛 ValueError，`_connect` 未捕获。 |
| P1-3 | `port.py:175-180` | **InputPort 无重连机制**：10 次×0.2s 内 buffer 未出现即永久 disconnected，后续数据静默丢弃。 |
| P1-4 | `nodeflow_sdk.py:97-109` | **ParentProcessWatchdog 对 ppid==1 进程误杀**：节点由 launchd/init 拉起时首个周期即 `os._exit(1)`；已记录 initial_ppid 却未做守卫。 |
| P1-5 | `shared_buffer_lite.py:30-37,103-115` | 写端无跨进程互斥（单写者假设未强制）。 |

### P2（中）

- `_PROCESS_LOCKS` 无限增长（每个唯一 path 一个 RLock 永不清除）。
- `write()` 每次两次 `mmap.flush()`（性能）。
- `recv_latest_blocking` 1ms 忙轮询（高 CPU，port.py:237）。
- `NODE_OUT_{name}_BUFFER_SIZE` 环境变量命名与框架 `NODE_OUT_<PORT>` 约定不一致（port.py:48）。
- `nodeflow_sdk.py:23` `logger=None` 死代码；`shutdown()` 未 close StructuredLogger。
- metadata 每次端口创建全量重写 O(N²)。
- 看门狗调用私有 API `atexit._run_exitfuncs()` 且从非主线程调用。
- `param_parser` 不校验顶层类型；无显式布尔 coercion（见验证 C4）。
- `structured_logger.py:78-86`：custom_fields 含不可序列化对象（numpy）→ 整条日志写入失败。
- `structured_logger.py:136`：同 node_id 二次实例化 `handlers.clear()` 泄漏旧 handler。

## 4. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C11: SharedBufferLite 读写 roundtrip（100 字符消息）+ 连续 5 次写入 seq 递增 1→6、最新值语义正确 | **通过**（核心协议自洽） |
| C4: `bool("false") == True`——字符串参数经 CLI 传入时逻辑反转（track_controller/tillage_controller/waypoint_selector/pwm_driver 均受影响，见 nodes 报告） | **确认** |

## 5. 总体评价

**优点**: tombstone + header 双重校验的写读协议设计自洽（实测 roundtrip 与 seq 递增正确）；注释明确解释了"只比 seq 不够必须连 length 校验"的原因；late-joiner 历史快照缓存合理；StructuredLogger 双输出与 per-handler 锁正确。

**主要风险**: InputPort 的三类可靠性短板（seq 归零断流、启动竞态崩溃、无重连）是节点数据链路的核心隐患；看门狗对 ppid==1 误杀在生产环境（launchd 拉起）下是致命风险。

**建议优先修复**: P1-1（检测到 diff 巨大或 seq 归零时重读快照并重置 last_sequence）、P1-2（`_connect` 对 0 字节文件重试/跳过）、P1-4（initial_ppid==1 时禁看门狗或放宽首周期）。
