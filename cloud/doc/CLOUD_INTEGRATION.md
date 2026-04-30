# NodeFlow 云端集成对接文档

> 面向云端开发团队的端侧对接接口规范。本文档描述了云端如何通过 MQTT + HTTP 向端侧 NodeFlow 运行时下发任务、监控执行状态。

---

## 1. 总体架构

```
┌── 云端 ───────────────────────────────────────────────────┐
│                                                            │
│  Job Manager ──→ Dispatch Service ──→ MQTT Broker          │
│  (任务编排)      (下发调度)           (mosquitto/EMQX)      │
│       │                            │                       │
│  Splitter        HTTP Server        │                      │
│  (地块分割)      (大文件存储)        │                      │
│                   ↑                 │                      │
└───────────────────┼─────────────────┼──────────────────────┘
                    │                 │
         HTTP 下载   │          MQTT  │ 控制/状态
         (路径文件)  │          (JSON)│
                    │                 │
┌── 端侧 (农机) ───┼─────────────────┼──────────────────────┐
│                  │                 ↓                       │
│  HTTP Client ────┘          Task Agent (MQTT Sub)          │
│  (大文件下载)                → TaskExecutor                 │
│                              → Runtime Daemon               │
│                              → 19 节点子进程 (数据流)       │
└────────────────────────────────────────────────────────────┘
```

**关键设计原则**:
- MQTT 承载控制指令、状态上报（< 4KB 消息体）
- HTTP 承载大文件下载（路径数据可达 10MB）
- 端侧不依赖云端也可独立运行（离线模式）

---

## 2. MQTT 通信

### 2.1 Broker 连接

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 协议 | MQTT 3.1.1 / 5.0 | 3.1.1 |
| 地址 | Broker URL | `localhost:1883` |
| Client ID | `nodeflow-{machine_id}` | `nodeflow-{hostname}` |
| Keep Alive | 心跳间隔 | 60s |
| Clean Session | false（断线恢复后保留订阅） | false |

端侧通过环境变量配置:
```bash
NF_MQTT_BROKER=mqtt://cloud-broker:1883
NF_MACHINE_ID=tractor-01
NF_TASK_AUTO_ACCEPT=false
NF_HTTP_SERVER_URL=http://cloud-api:8080
```

### 2.2 Topic 定义

#### 云端 → 端侧

| Topic | QoS | 消息体 | 说明 |
|-------|-----|--------|------|
| `nodeflow/{machine_id}/task/dispatch` | 1 | [TaskDispatch](#33-taskdispatch---任务下发) | 下发新任务 |
| `nodeflow/{machine_id}/task/cancel` | 1 | [TaskCancel](#34-taskcancel---任务取消) | 取消任务 |

#### 端侧 → 云端

| Topic | QoS | 消息体 | 说明 |
|-------|-----|--------|------|
| `nodeflow/{machine_id}/status` | 0 | [TaskStatus](#35-taskstatus---状态上报) | 任务状态变更/进度 |
| `nodeflow/{machine_id}/heartbeat` | 0 | [Heartbeat](#36-heartbeat---机器心跳) | 机器心跳（30s 间隔） |
| `nodeflow/{machine_id}/task/ack` | 1 | [TaskAck](#37-taskack---任务确认) | 任务接收确认 |

#### 通配符订阅

云端如需监听所有机器:
```
nodeflow/+/heartbeat    # 所有机器心跳
nodeflow/+/status       # 所有机器状态
```

### 2.3 消息格式

所有 MQTT 消息体为 JSON 格式，UTF-8 编码，无压缩。

#### 2.3.1 TaskDispatch — 任务下发

**Topic**: `nodeflow/{machine_id}/task/dispatch`  
**QoS**: 1（至少一次送达）  
**触发时机**: 云端完成 Job 编排和地块分割后

```json
{
  "type": "task_dispatch",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_id": "job-20260427-001",
  "dispatch_id": "dispatch-uuid-unique-per-attempt",
  "preset_yaml": "tillage_operation",
  "operation_type": "tillage",
  "sequence_index": 0,
  "machine_id": "tractor-01",
  "parcel_ref": "field_A_east_section_3",
  "parcel_url": "http://cloud-api:8080/api/v1/parcels/field_A_east_section_3.json",
  "path_url": "http://cloud-api:8080/api/v1/paths/550e8400-....bin",
  "node_params": {
    "parcel_planner": {
      "parcel_name": "field_A_east"
    },
    "trajectory_loader": {
      "trajectory_file": ""
    },
    "sim_output": {
      "simulator_host": "192.168.1.100",
      "simulator_port": 5555
    }
  },
  "timestamp": 1777228958.123
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✓ | 固定值 `"task_dispatch"` |
| `task_id` | string | ✓ | 任务唯一 ID（UUID） |
| `job_id` | string | ✓ | 父 Job ID，用于编排和多机关联 |
| `dispatch_id` | string | ✓ | 本次下发唯一 ID，重试时变化，端侧用于去重 |
| `preset_yaml` | string | ✓ | 预设配置名，对应端侧 `examples/{name}.yaml` |
| `operation_type` | string | ✓ | 作业类型: `tillage` / `seeding` / `spraying` |
| `sequence_index` | int | ✓ | 在 Job 操作链中的位置，从 0 开始 |
| `machine_id` | string | ✓ | 目标机器 ID |
| `parcel_ref` | string | | 地块引用名（人类可读） |
| `parcel_url` | string | | 地块数据 HTTP URL（GeoJSON），< 100KB |
| `path_url` | string | | 路径数据 HTTP URL（MsgPack 二进制），可达 10MB |
| `node_params` | object | ✓ | 节点参数覆盖，格式: `{"node_id": {"param": val}}` |
| `timestamp` | float | ✓ | Unix 时间戳（秒） |

#### 2.3.2 TaskCancel — 任务取消

**Topic**: `nodeflow/{machine_id}/task/cancel`  
**QoS**: 1

```json
{
  "type": "task_cancel",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "machine_id": "tractor-01",
  "reason": "operator_request",
  "timestamp": 1777229000.456
}
```

**reason 枚举值**:
- `operator_request` — 操作员主动取消
- `job_cancelled` — 父 Job 被取消
- `machine_unavailable` — 机器离线/不可用
- `replan` — 重新规划需要

#### 2.3.3 TaskStatus — 状态上报

**Topic**: `nodeflow/{machine_id}/status`  
**QoS**: 0（best-effort，非实时）  
**上报频率**:
- 状态变更（PENDING→READY→RUNNING→COMPLETED/FAILED）：立即上报
- 进度更新：每 60 秒上报一次

```json
{
  "type": "task_status",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "machine_id": "tractor-01",
  "state": "running",
  "progress_pct": 45.0,
  "current_node": "track_controller",
  "nodes_healthy": 8,
  "nodes_total": 9,
  "error_code": "",
  "error_detail": "",
  "timestamp": 1777229358.456
}
```

**state 状态机**:

```
PENDING → DOWNLOADING → READY → RUNNING → COMPLETED
                                             ↓
PENDING → DOWNLOADING → READY → RUNNING → FAILED
                       ↓
                    CANCELLED（任意阶段）
```

| state | 含义 |
|-------|------|
| `pending` | 已接收任务，等待确认/开始 |
| `downloading` | 正在从 HTTP 下载大文件（parcel/path） |
| `ready` | 所有数据就绪，等待执行 |
| `running` | 数据流执行中（农机作业中） |
| `completed` | 任务成功完成 |
| `failed` | 任务失败（见 error_detail） |
| `cancelled` | 已被云端或操作员取消 |

#### 2.3.4 Heartbeat — 机器心跳

**Topic**: `nodeflow/{machine_id}/heartbeat`  
**QoS**: 0  
**间隔**: 30 秒  
**离线判定**: 连续 5 分钟无心跳

```json
{
  "type": "heartbeat",
  "machine_id": "tractor-01",
  "state": "busy",
  "current_task_id": "550e8400-e29b-41d4-a716-446655440000",
  "cpu_pct": 23.5,
  "memory_mb": 512.3,
  "disk_free_gb": 15.2,
  "runtime_uptime_seconds": 36000,
  "timestamp": 1777229400.000
}
```

**machine state 枚举**:
- `idle` — 空闲，无任务执行
- `busy` — 正在执行任务
- `error` — 运行时故障

#### 2.3.5 TaskAck — 任务确认

**Topic**: `nodeflow/{machine_id}/task/ack`  
**QoS**: 1  
**触发**: 端侧收到 `task_dispatch` 后立即回复

```json
{
  "type": "task_ack",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "dispatch_id": "dispatch-uuid-unique-per-attempt",
  "machine_id": "tractor-01",
  "accepted": true,
  "reject_reason": "",
  "timestamp": 1777228960.789
}
```

**云端重试策略**: 下发后 30s 内未收到匹配 `dispatch_id` 的 ACK → QoS 1 自动重试，最多 3 次。

---

## 3. HTTP API

### 3.1 地块数据端点

```
GET /api/v1/parcels/{parcel_ref}.json
```

**响应** (GeoJSON, < 100KB):
```json
{
  "parcel_id": "field_A_east_section_3",
  "type": "Polygon",
  "coordinates": [
    [
      [120.037328, 28.916850],
      [120.038500, 28.916850],
      [120.038500, 28.917900],
      [120.037328, 28.917900],
      [120.037328, 28.916850]
    ]
  ],
  "vehicle_config": {
    "implement_width_m": 2.0,
    "overlap_ratio": 0.1,
    "path_inset_m": 0.5
  },
  "ref_point": {
    "lon": 120.037328,
    "lat": 28.916850
  }
}
```

**注意**:
- 如果地块已预计算 ENU 坐标，可附加 `enu_outer` 字段直接使用
- `vehicle_config` 可省略（端侧已有默认值）

### 3.2 路径数据端点

```
GET /api/v1/paths/{task_id}.bin
```

**响应** (MsgPack 二进制, Content-Type: `application/octet-stream`):
```python
# 端侧解码后的结构
{
    "task_id": "550e8400-...",
    "timestamp": 1777228900.0,
    "path": [(x1, y1), (x2, y2), ..., (xn, yn)],  # ENU 坐标列表
    "status": "success",
    "message": "Path generated for field_A_east"
}
```

**格式说明**:
- 序列化: MsgPack（非 JSON），Python `msgpack.packb(dict)`
- 路径点: `(float, float)` 元组数组
- 文件大小: 密集路径（0.5m 间距）约 10MB/100亩
- **必须支持 HTTP Range 请求**（断点续传）
- 响应头必须包含 `Content-Length` 和 `X-Checksum-SHA256`

**SHA-256 校验**: 响应头 `X-Checksum-SHA256` 包含文件哈希，端侧下载完成后校验。

### 3.3 通用要求

| 要求 | 说明 |
|------|------|
| 认证 | HTTP Bearer Token（端侧通过 `NF_API_TOKEN` 环境变量提供） |
| 超时 | parcel ≤ 30s, path ≤ 300s（10MB 弱网下载） |
| 重试 | 端侧最多重试 3 次，指数退避（2s/4s/8s） |
| 压缩 | 路径数据可选 gzip（`Accept-Encoding: gzip`），节约 30-50% |

---

## 4. 任务执行流程

### 4.1 单机单步骤（离线模式，无云端）

```
操作员:
  $ nodeflow runtime start examples/tillage_operation.yaml --daemon
  $ nodeflow task run examples/tillage_task.yaml

端侧内部:
  YAML → Task 对象
  → TaskExecutor 写入 runtime.control buffer
  → Daemon 轮询到命令 → 注入 node_params → start_dataflow()
  → 节点子进程层层启动 → 数据流运行
```

### 4.2 云端下发单任务

```
Cloud                              Edge
  │                                  │
  │── MQTT task/dispatch ──────────→│ QoS 1
  │                                  ├─ 去重检查 (dispatch_id)
  │←── MQTT task/ack ───────────────│ QoS 1
  │                                  ├─ 若 parcel_url 存在: HTTP GET 下载地块
  │                                  ├─ 若 path_url 存在: HTTP GET 流式下载路径
  │                                  ├─ 写入 runtime.control buffer
  │                                  │
  │←── MQTT status (DOWNLOADING) ──│ QoS 0
  │←── MQTT status (READY) ────────│ QoS 0
  │←── MQTT status (RUNNING) ──────│ QoS 0
  │         ... (每60s 进度) ...     │
  │←── MQTT status (COMPLETED) ────│ QoS 0
```

### 4.3 多机分割 + 任务链（旋耕 → 播种）

```
1. 云端创建 Job
   Job: {
     steps: [tillage(seq=0), seeding(seq=1, depends_on=0)],
     machines: [tractor-01, tractor-02],
     parcel: <大地块 GeoJSON>
   }

2. 云端自动分割
   Splitter: 大地块 → 2 个子地块 (strip 算法)
   → 生成 2 个 tillage 子任务
   → 下发到 tractor-01、tractor-02

3. 等待所有 tillage 任务完成
   Cloud 监听 status topic
   → tractor-01 tillage COMPLETED ✓
   → tractor-02 tillage COMPLETED ✓

4. 触发下一个步骤
   → 生成 2 个 seeding 子任务（复用分割结果）
   → 下发到 tractor-01、tractor-02

5. 全部完成
   → Job COMPLETED
```

---

## 5. node_params 参数说明

`node_params` 是任务下发中最关键的字段，用于覆盖预设 YAML 中的节点参数。格式为:

```json
{
  "<node_id>": {
    "<param_name>": <value>
  }
}
```

**常用覆盖参数**（按节点）:

| 节点 ID | 参数 | 类型 | 说明 |
|---------|------|------|------|
| `parcel_planner` | `parcel_name` | string | 地块文件名 |
| `trajectory_loader` | `trajectory_file` | string | 轨迹文件路径 |
| `sim_output` | `simulator_host` | string | 仿真器地址 |
| `sim_output` | `simulator_port` | int | 仿真器端口 |
| `global_coverage` | `path_point_spacing` | float | 路径点间距 (m) |
| `track_controller` | `max_speed` | float | 最大速度 (m/s) |
| `rtk_driver` | `device` | string | RTK 串口设备 |
| `rtk_driver` | `baud` | int | 波特率 |

**参数注入机制**:
1. 云端 → MQTT `dispatch` 消息携带 `node_params`
2. 端侧 TaskAgent 接收 → 写入 `runtime.control` 缓冲区
3. Daemon 读取 → `_apply_node_params()` → merge 到 `NodeInstance.params`
4. 节点启动时 → `--params '{"parcel_name":"field_A",...}'` 命令行
5. SDK `get_param("parcel_name")` → 拿到 "field_A"

---

## 6. 错误处理

### 6.1 端侧错误码（status.error_code）

| 错误码 | 含义 | 建议处理 |
|--------|------|----------|
| `PAYLOAD_DOWNLOAD_FAILED` | 大文件 HTTP 下载失败 | 检查 HTTP 端点，3 次重试耗尽 |
| `PARCEL_NOT_FOUND` | 地块文件不存在 | 检查 parcel_ref 是否正确 |
| `PRESET_NOT_FOUND` | preset_yaml 指定的配置不存在 | 检查 preset 名称拼写 |
| `NODE_CRASH` | 节点进程崩溃 | 已触发自动重启（最多 3 次），超限后报错 |
| `GRAPH_START_FAILED` | 数据流图启动失败 | 检查 runtime.yaml 配置 |
| `TIMEOUT` | 任务超时 | 检查预估作业时间，调整超时设置 |

### 6.2 云端应处理的场景

| 场景 | 端侧行为 | 云端应做 |
|------|----------|----------|
| MQTT 下发后无 ACK | 端侧可能离线或 MQTT 断连 | 30s 超时重试，3 次后标记 FAILED |
| 重复下发 (相同 dispatch_id) | 端侧 TaskStore 去重，忽略 | 每个重试使用新的 dispatch_id |
| 任务执行中机器离线 | 端侧继续执行（离线模式），上线后补报状态 | 5 分钟无心跳 → 标记 UNKNOWN，等待恢复 |
| HTTP 下载超时 | 端侧重试 3 次 | 确保 HTTP 端点可用，支持 Range |
| 任务取消 | 端侧发送 stop_dataflow → 终止所有节点子进程 | 更新 Job 状态，如需可重新下发 |

---

## 7. 常用预设 YAML 列表

端侧 `examples/` 目录下的可用预设配置:

| Preset 名称 | 用途 | 节点数 | 适用场景 |
|-------------|------|--------|----------|
| `tillage_operation` | 旋耕作业（运动+机具控制） | 10 | 旋耕、犁地等机具操作 |
| `planning_simulation` | 仿真全链路 | 8 | 测试、仿真环境 |
| `planning_with_real_rtk` | 真机 RTK 规划控制 | 7 | 实际田间作业 |
| `trajectory_playback` | 轨迹回放控制 | 7 | 复现录制路径 |
| `manual_trajectory_recording` | 轨迹录制 | 4 | 录制人工驾驶轨迹 |
| `web_pwm_teleop` | Web 遥控 | 4 | 手动遥控调试 |
| `sim_arc_tracker` | Arc 跟踪仿真 | 6 | 转弯/弧线测试 |

**选择 preset 的建议**:
- 纯运动控制（无农机具）→ `planning_with_real_rtk` 或 `trajectory_playback`
- 需要农机具联动（旋耕/播种）→ `tillage_operation`
- 仿真测试 → `planning_simulation`

---

## 8. 兼容性承诺

### 向后兼容
- 新增字段不会破坏旧版端侧（未知字段被忽略）
- `node_params` 仅覆盖已存在节点/参数，未知 node_id 被跳过并告警
- 端侧离线模式不依赖 MQTT/HTTP，纯本地 YAML 驱动

### 版本协商（未来）
- MQTT `dispatch` 消息预留 `protocol_version` 字段（当前默认 "1.0"）
- HTTP 响应头 `X-NodeFlow-Version` 标记 API 版本

---

## 9. 快速验证（本地测试）

云端开发者无需真实农机即可验证端到端协议:

```bash
# 1. 启动 MQTT broker
mosquitto -p 1883 &

# 2. 启动端侧 daemon（仿真模式）
nodeflow runtime start examples/tillage_operation.yaml --daemon

# 3. 模拟云端下发任务
mosquitto_pub -t 'nodeflow/tractor-01/task/dispatch' \
  -m '{
    "type":"task_dispatch",
    "task_id":"test-'$(uuidgen)'",
    "job_id":"test-job-001",
    "dispatch_id":"test-dispatch-001",
    "preset_yaml":"tillage_operation",
    "operation_type":"tillage",
    "sequence_index":0,
    "machine_id":"tractor-01",
    "node_params":{
      "parcel_planner":{"parcel_name":"demo_field"},
      "trajectory_loader":{"trajectory_file":""}
    },
    "timestamp":'$(date +%s)'
  }' -q 1

# 4. 观察端侧状态上报
mosquitto_sub -t 'nodeflow/tractor-01/status' -v
```
