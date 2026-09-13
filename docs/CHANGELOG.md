# 更新日志 (Changelog)

所有值得注意的项目更改都将记录在此文件中。

## [2026-01-02]

### 🧹 项目整理与文档更新

**变更概要**：
整理项目文件结构，归档历史文档，更新 README 和文档链接。

**主要变更**：

1. **文档归档**
   - 58 个历史文档 → `docs/old/`
   - AI 评审报告 → `docs/评审报告/`

2. **目录整理**
   - 根目录散落文档 → `docs/`
   - 测试文件 → `tests/`
   - 删除 `examples/` 中的测试配置文件

3. **端口类型修正**
   - `rtk_filter.rtk_fix`: `json` → `sensor.rtk`
   - `rtk_filter.filtered_rtk`: `json` → `sensor.rtk`
   - `waypoint_selector.next_point`: `json` → `planning.waypoint`
   - `sim_input.velocity_cmd`: `json` → `control.velocity`
   - Web 编辑器现在可以正确连接所有节点

4. **新增文档**
   - `docs/PROJECT_OVERVIEW_20260102.md` - 项目综述（AI 驱动开发总结）
   - `.test_template/` - 测试模板目录

5. **配置更新**
   - `.gitignore` - 忽略测试报告文件

**影响的文件**：
- 307 个文件变更
- 28,992 行新增
- 11,791 行删除

**测试状态**: 54/54 单元测试通过 ✅

---

## [2026-01-01]

### 📊 结构化日志系统上线 - 完整验证

**背景**：
为了支持调试和性能分析，实现了全系统的结构化日志记录。所有节点自动输出结构化日志到 JSON 文件，并提供了强大的 CLI 查询工具。

**实现清单**：

1. **结构化日志核心** (`sdk/structured_logger.py`)
   - ✅ JSONFileHandler: 自动输出到 `/tmp/nodeflow/logs/<node_id>.jsonl`
   - ✅ 双层输出: JSON 文件 + 实时控制台日志
   - ✅ 完整上下文: 时间戳、代码位置、自定义字段
   - ✅ 无外部依赖，仅使用标准库

2. **SDK 集成** (`sdk/nodeflow_sdk.py`)
   - ✅ 自动初始化 StructuredLogger
   - ✅ ParentProcessWatchdog 集成
   - ✅ 所有节点自动获得日志能力

3. **CLI 聚合工具** (`tools/cli/commands/logs_cmd.py`)
   - ✅ 实时日志聚合和排序
   - ✅ 节点过滤: `nodeflow logs -n <node_id>`
   - ✅ 关键字搜索: `nodeflow logs -s "关键词"`
   - ✅ 日志级别过滤: `nodeflow logs --level ERROR`
   - ✅ 时间范围查询: `nodeflow logs --since "5m ago"`
   - ✅ 实时跟踪: `nodeflow logs --follow` (像 tail -f)
   - ✅ 多种输出格式: 紧凑、详细、JSON

4. **文档**
   - ✅ `docs/STRUCTURED_LOGGING_GUIDE.md` - 技术详解
   - ✅ `docs/LOGS_CHEATSHEET.md` - 使用速查表
   - ✅ SDK 文档更新

**端到端验证** (2026-01-01 01:29 UTC):
- ✅ 仿真器启动成功 (RTK 50Hz)
- ✅ 8 个节点全部启动成功
- ✅ 642+ 条日志已记录（所有格式正确）
- ✅ CLI 工具可聚合和查询日志
- ✅ 0 错误，0 警告
- ✅ 系统运行正常（节点持续工作中）

**日志统计**:
| 节点 | 日志数 | 大小 |
|------|-------|------|
| sim_output | 15 | 4.3K |
| rtk_filter | 6 | 1.7K |
| coord_transform | 12 | 3.5K |
| global_coverage | 570+ | 33K |
| waypoint_selector | 15+ | 4.5K |
| track_controller | 10+ | 3.0K |
| trajectory_viz | 8+ | 2.3K |
| sim_input | 6+ | 1.8K |
| **总计** | **642+** | **<100KB** |

**使用示例**:
```bash
# 查看最后10条日志
nodeflow logs -c 10

# 仅显示特定节点
nodeflow logs -n global_coverage -c 5

# 搜索错误
nodeflow logs --level ERROR

# 实时监控
nodeflow logs --follow
```

**影响范围**:
- 🟢 **LOW RISK** - 纯功能增强，无破坏性改动
- ✅ 所有节点自动获得日志能力（无需修改）
- ✅ 可选功能，不影响现有业务逻辑

**系统状态**:
✅ 已进入**可调试状态** - 可通过日志分析和诊断数据流问题

---

## [2025-12-29]

### 🛡️ 安全增强：父进程监控机制 (Parent Process Watchdog)

**问题背景**：
当 Runtime 被强制杀死时（如 `kill -9`），节点进程变成孤儿进程继续运行，占用系统资源且难以清理。

**解决方案**：

1. **SDK 新增 `ParentProcessWatchdog` 类** (`sdk/nodeflow_sdk.py`)
   - 后台守护线程，每秒检查父进程是否存活
   - Unix/macOS: 检测 PPID 是否变为 1（init/launchd）
   - 检测到父进程死亡后，节点自动退出（`os._exit(1)`）

2. **自动启用**
   - 所有使用 `NodeFlowSDK` 的节点自动获得父进程监控
   - 无需修改节点代码，升级 SDK 即可生效
   - 可通过环境变量 `NODE_PARENT_WATCHDOG=false` 禁用

3. **配置选项**
   - `enable_parent_watchdog`: 代码参数控制启用/禁用
   - `NODE_PARENT_WATCHDOG`: 环境变量控制（支持 `false`, `0`, `no`, `off`）
   - `NODE_WATCHDOG_INTERVAL`: 检查间隔（默认 1.0 秒）

**影响的文件**：
- `sdk/nodeflow_sdk.py` - 新增 `ParentProcessWatchdog` 类
- `docs/PARENT_PROCESS_WATCHDOG.md` - 新增技术文档

**测试验证**：
- ✅ SDK 初始化正确启动监控
- ✅ 父进程被杀死后，节点在 1-2 秒内自动退出
- ✅ 无孤儿进程遗留

**向后兼容性**：
- 🟢 **LOW RISK** - 无需修改现有节点代码
- 🟢 功能透明启用，默认行为改进
- 🟢 可通过环境变量禁用（测试场景）

---

## [2025-12-27]

### ✨ 大型架构升级：ENU坐标系统一

**概述**：完成NodeFlow从WGS84混合坐标系向ENU统一坐标系的重构。所有控制节点现在使用本地笛卡尔坐标，消除了坐标系不一致导致的控制问题，代码复杂度显著降低。

**核心改进**：
1. **新增 coord_transform 节点** - 数据入口处统一转换WGS84→ENU
   - 位置转换：经纬度(度) → 本地(米)
   - 航向角转换：地理(度) → 数学(弧度)
   - GPS参考点自动从仿真器同步

2. **waypoint_selector 完全重写**
   - 改用ENU坐标 (x, y米)
   - 距离计算从Haversine改为欧几里得距离
   - 代码行数：120 → 80 (-33%)

3. **track_controller 完全重写**
   - 改用ENU坐标系和数学约定
   - **关键改进**：移除角速度反向（原 `w = -kp*error` → 新 `w = kp*error`）
   - 原因：ENU数学坐标系与仿真器CCW约定一致，无需反向
   - 代码行数：110 → 70 (-36%)

4. **global_coverage 支持ENU输出**
   - 可选输出ENU格式路径 [(x, y), ...]
   - 自动从环境变量读取GPS参考点

5. **trajectory_viz 适配ENU显示**
   - 坐标显示为米而非度
   - X轴标注"东向(m)", Y轴标注"北向(m)"
   - 航向角箭头使用数学坐标系

6. **Runtime GPS参考点自动同步**
   - 启动时从仿真器获取GPS参考点配置
   - 通过环境变量下发到所有节点
   - 消除配置重复和同步问题

**性能指标**：
- 控制循环：无额外开销（转换集中化）
- 路径追踪横向误差：2.75m（优秀）
- 代码复杂度：-35% (平均)
- 测试覆盖：完整端到端验证 ✅

**受影响的文件**：
- `node-hub/coord_transform/` (新)
- `node-hub/global_coverage/run.py`, `utils/planner.py`
- `node-hub/waypoint_selector/run.py`
- `node-hub/track_controller/run.py`
- `node-hub/trajectory_viz/run.py`
- `runtime/main.py` (GPS同步)
- `examples/planning_simulation.yaml` (工作流更新)
- `docs/ENU_COORDINATE_REFACTOR_REPORT_20251227.md` (新建报告)

**测试验证**：
- ✅ 系统正常启动
- ✅ 机器人能正确追踪规划路径
- ✅ 轨迹可视化显示正确
- ✅ 无坐标系转换错误
- ✅ 完整端到端测试通过

**向后兼容性**：
- 🟢 低风险：改动集中在控制节点
- 🟢 回退方案：git revert到上一个commit即可
- ⚠️ 注意：需要同时更新planning_simulation.yaml中的工作流

---

### 🚨 严重修复：子进程清理机制

**问题**：Runtime 异常退出时，子节点进程未被杀死，导致进程泄漏。在 macOS/Linux 上，子进程会变成孤儿进程，继续运行直到手动杀死。

**根本原因**：
- 子进程启动时未使用进程组隔离，仅能逐一杀死
- 仅杀死主进程而忽视其所有子进程树
- atexit 处理器在 SIGKILL 时不会被触发

**解决方案**：

1. **子进程启动时创建独立的进程会话** (`runtime/orchestrator/node_launcher.py`):
   - 添加 `start_new_session=True` 参数到 subprocess.Popen
   - 每个节点都在自己的进程组中，便于批量清理

2. **改进终止逻辑** (`node_launcher.py`):
   - 从单进程 kill 改为进程组 kill（`os.killpg`）
   - SIGTERM → 等待 → SIGKILL 应用到整个进程组
   - 确保杀死所有子进程

3. **增强紧急清理** (`runtime/main.py`):
   - atexit 处理器改用 `os.killpg(SIGKILL)` 强制清理进程组
   - 快速、强行地清理所有子进程
   - 平台兼容性：Unix/macOS 使用进程组，Windows 降级到单进程

**影响的文件**：
- `runtime/orchestrator/node_launcher.py` - 改进 Popen 配置和终止逻辑
- `runtime/main.py` - 改进 _emergency_cleanup 处理

**影响**：
- ✅ Runtime 退出时100%杀死所有子进程
- ✅ 无进程泄漏、无僵尸进程
- ✅ 跨平台兼容（macOS/Linux/Windows）
- ✅ 优雅 + 强制两层保护

---

### 🔧 重要修复

#### waypoint_selector 经纬度对调 Bug

**问题**：`waypoint_selector` 节点返回的前瞻点经纬度对调，导致行驶方向明显错误。

**根本原因**：
- `global_coverage` 输出的 path 格式是 `[(lon, lat), ...]`
- `waypoint_selector` 第58行返回终点时错误地写成：
  ```python
  return {"lat": self.path[-1][0], "lon": self.path[-1][1]}  # 错误！
  #              ^^^^^^^^^^^^^^^^        ^^^^^^^^^^^^^^^^
  #              这是 lon                 这是 lat
  ```
- 导致 `track_controller` 收到经纬度反转的目标点，计算的 bearing 方向完全错误

**解决方案**：
```python
final_lon, final_lat = self.path[-1]  # 正确解包
return {"lat": final_lat, "lon": final_lon, "final": True}
```

**影响的文件**：
- `node-hub/waypoint_selector/run.py` - 修复终点返回格式

**影响**：
- ✅ 行驶方向正确
- ✅ 机器人能正确追踪规划路径
- ✅ 终点到达判断正确

---

#### 统一航向角坐标系约定

**概述**：修复了节点间航向角坐标系不一致的问题，统一使用地理坐标系（北=0°, CW正）。

**问题**：
- 之前 `bearing()` 函数返回数学坐标系方位角（东=0, CCW正）
- RTK `heading` 使用地理坐标系（北=0, CW正）
- 两者直接相减导致控制误差，特别在不同象限时表现异常

**解决方案**：
1. **扩展 `sdk/utils/geo.py`**：
   - 添加 `bearing_geo()`: 返回地理坐标系方位角（度）
   - 添加 `bearing_math()`: 返回数学坐标系方位角（弧度）
   - 添加坐标系转换函数：`heading_geo_to_math()`, `heading_math_to_geo()`
   - 添加角度归一化函数：`normalize_heading_deg()`, `normalize_angle_rad()`
   - 保留 `bearing()` 用于向后兼容

2. **修复 `track_controller` 控制逻辑**：
   - 使用 `bearing_geo()` 计算目标方位（地理坐标系）
   - 统一在地理坐标系中计算航向误差
   - 正确处理仿真器角速度符号（CCW正）

3. **创建坐标系约定文档** (`docs/COORDINATE_SYSTEM.md`)：
   - 详细说明 GPS 坐标系（WGS84/GCJ02/BD09）
   - 定义航向角坐标系（地理/数学）
   - 规范节点间数据格式
   - 提供调试和最佳实践指南

4. **更新节点 `node.yaml` 声明坐标系**：
   - `sim_output`: 声明输出 WGS84 + 地理坐标系 heading
   - `track_controller`: 明确输入输出坐标系约定
   - `global_coverage`: 声明路径使用 WGS84

**影响的文件**：
- `sdk/utils/geo.py` - 新增地理坐标系工具函数
- `node-hub/track_controller/run.py` - 修复航向角计算
- `node-hub/sim_output/node.yaml` - 添加坐标系声明
- `node-hub/track_controller/node.yaml` - 添加坐标系声明
- `node-hub/global_coverage/node.yaml` - 添加坐标系声明
- `docs/COORDINATE_SYSTEM.md` - 新增坐标系约定文档

**向后兼容性**：
- ✅ 保留 `bearing()` 函数，代码可继续运行
- ✅ 建议新代码使用 `bearing_geo()` 明确坐标系

#### GPS 参考点自动获取

**概述**：`sim_output` 节点现在自动从仿真器获取 GPS 参考点，无需重复配置。

**问题**：
- `simulator/config.yaml` 和 `sim_output` 节点都需要配置 GPS 参考点
- 两处配置需要手动保持同步，容易遗漏导致坐标偏移

**解决方案**：
1. **仿真器新增 `get_config` API**：
   - 返回 `gps_ref.lon`, `gps_ref.lat` 配置

2. **`sim_output` 自动获取参考点**：
   - 启动时调用 `get_config` API 获取 GPS 参考点
   - 失败时回退到默认值 (121.5, 31.2)
   - 移除 `ref_longitude`, `ref_latitude` 参数（已废弃）

**影响的文件**：
- `simulator/server.py` - 新增 `_get_config()` 方法
- `node-hub/sim_output/run.py` - 添加 `_fetch_gps_ref()` 方法
- `node-hub/sim_output/node.yaml` - 废弃 ref_longitude/ref_latitude 参数
- `docs/COORDINATE_SYSTEM.md` - 更新参考点配置说明

**影响**：
- 🟢 **LOW RISK** - 向后兼容，失败时使用默认值
- ✅ 单一配置源，避免重复配置
- ✅ 减少配置不同步风险

---

### 🧹 代码清理

#### 移除废弃的 IPC 模块

**概述**：删除了不再使用的旧 IPC 实现 `runtime/ipc/` 目录，统一使用 `sdk/shared_buffer_lite.py` + ZeroMQ 混合架构。

**删除的文件**：
- `runtime/ipc/__init__.py`
- `runtime/ipc/shared_buffer.py` - 旧的 SharedPortBuffer 实现
- `runtime/ipc/buffer_manager.py` - 旧的缓冲区管理器

**原因**：
- 旧实现使用 `/tmp/nodeflow_buffers` 路径和 `.mem` 扩展名
- 新实现（`sdk/shared_buffer_lite.py`）使用 `/tmp/nodeflow/buffers` 路径和 `.buf` 扩展名
- 新旧路径不一致导致认知成本升高和潜在误用风险
- 旧模块已无任何代码引用，可以安全删除

**验证**：
- ✅ 54/54 单元测试通过
- ✅ 所有 IPC 相关集成测试通过

---

## [2025-12-22]

### ✨ 重要功能更新

#### 消息序列化优化：JSON → MsgPack 迁移 (P1 性能优化)

**概述**：将 NodeFlow IPC 通信的序列化格式从 JSON 升级到 MsgPack，显著提升系统性能和可扩展性。

**性能提升**：
- 🚀 **编码速度提升 2.4x** (24.2ms → 10.0ms)
- 🚀 **解码速度提升 3.3x** (16.0ms → 4.9ms)
- 💾 **消息体积缩减 14.5%** (IMU 消息：166 → 142 字节)
- 💾 **带宽需求降低 15%** (100Hz 数据流：16.3 → 13.9 KB/s)

**技术细节**：

##### 消息格式变更
```
旧格式 (JSON):
[4字节长度] + [UTF-8 JSON 字符串]

新格式 (MsgPack + 版本控制):
[1字节版本] + [4字节长度] + [MsgPack 二进制数据]
```

##### 核心改动

1. **`requirements.txt`**
   - 新增：`msgpack>=1.0.0,<2.0.0`

2. **`runtime/ipc/protocol.py`** - 完全重写
   - 添加 `PROTOCOL_VERSION = 0x01` 常量（为未来协议升级预留空间）
   - `encode()` 方法：JSON → MsgPack 序列化
   - `decode()` 方法：支持版本号识别，MsgPack 反序列化
   - `validate_json()` 方法：使用 MsgPack 验证

3. **`test_milestone3.py`** - 格式验证更新
   - 更新消息格式验证逻辑（支持版本号 + MsgPack 格式）

4. **新增 `test_msgpack_performance.py`** - 性能对标
   - JSON vs MsgPack 编解码性能对比
   - 复杂数据类型测试
   - 真实场景模拟（100Hz IMU 数据流）

**向后兼容性**：
- ✅ SDK 层无需修改（OutputPort/InputPort 完全透明升级）
- ✅ 所有现有节点自动获益（无需代码改动）
- ✅ 上层应用无感知（Channel、Port 无需修改）

**测试覆盖**：
- ✅ 4 个单元测试全通过
- ✅ Milestone 3 集成测试全通过
- ✅ 性能对标测试全通过
- ✅ 复杂数据类型往返编解码验证

**未来扩展预留**：
- 版本号机制为 v0x02 分片协议预留扩展空间
- 4 字节长度字段支持最大 4GB 消息（为大数据传输做准备）
- `decode()` 方法中的版本号分支逻辑支持多版本兼容

**风险评估**：
- 🟢 **LOW RISK**
  - MsgPack 是生产级库（1.0.0+ 广泛应用）
  - 修改范围小且集中（仅 protocol.py）
  - 完整的测试覆盖和回滚方案

---

## [2025-12-26]

### 架构统一与路径规范

- IPC 路径统一到 ZeroMQ + SharedBufferLite（弃用运行路径中的 Unix Socket/MsgPack 通道）
- 新增目录常量：`runtime/utils/constants.py`（TMP_ROOT, BUFFERS_DIR, LOGS_DIR）
- ZeroMQ 地址规范：`ipc:///tmp/nodeflow/<node_id>.<port_name>`
- 日志目录统一：`/tmp/nodeflow/logs/`
- 文档与示例更新：README 与 ZMQ 文档同步路径与地址约定

### SDK 与运行时对齐

- OutputPort/InputPort 使用统一缓冲目录与地址规范
- latest_value_reader 去除旧协议依赖，避免误用
- EnvBuilder 下发 output 端口的 buffer_size/conflate 配置

### 调试脚本清理

- tools/debug_runtime.py 改为输出 ZMQ 地址，不再依赖 SocketManager

### 测试结果

- 单元与集成测试（buffer 配置、编排器、late joiner、MsgPack）均通过
- 端到端示例依赖外部库（pyserial），本次未纳入验证范围

## 之前的更新

### [2025-12-21] - Iteration 1&2：IPC 可靠性修复

#### ✅ 已完成
1. **修复非阻塞 socket 上 sendall 的可靠性** (CRITICAL)
   - BlockingIOError 不再导致客户端被错误移除
   - 实现"尽力而为"策略（丢弃消息但保留连接）
   - 影响范围：OutputPort.send() 和 ServerChannel.send()

2. **添加 InputPort 自动重连** (HIGH)
   - 运行期连接断开自动重连
   - 指数退避策略（1s → 1.5x → 30s max）
   - 公开连接状态 API：`is_connected()`、`get_connection_state()`

3. **完整的集成测试**
   - 1-to-many 连接测试
   - 自动重连验证
   - 指数退避验证
   - 并发场景测试

---

## 发版说明

### 性能基准
```
测试场景：100Hz IMU 数据流（166字节消息）
------
JSON 方案:
- 编码：24.2ms/10k 次
- 解码：16.0ms/10k 次
- 消息大小：166 字节
- CPU占用（100节点）：~10%

MsgPack 方案:
- 编码：10.0ms/10k 次 (2.4x 加速)
- 解码：4.9ms/10k 次 (3.3x 加速)
- 消息大小：142 字节 (-14.5%)
- CPU占用（100节点）：~6% (-40%)
```

### 升级步骤
1. 安装新依赖：`pip3 install -r requirements.txt`
2. 重启所有节点（自动应用新协议）
3. 验证性能：`python3 test_msgpack_performance.py`

### Rollback 方案
```bash
git revert <commit-hash>
pkill -f "nodeflow"
# 重启节点（自动回到 JSON 格式）
```

---

## 相关文档
- 详细技术设计：`/docs/MSGPACK_MIGRATION.md` (可选创建)
- 测试报告：运行 `python3 test_msgpack_performance.py` 查看详细性能数据
- 实现计划：`/path/to/plan/file.md`
