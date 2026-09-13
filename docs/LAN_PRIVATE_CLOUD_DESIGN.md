# NodeFlow 农场局域网私有云设计

> 状态: v0.1 设计基线
> 更新时间: 2026-06-01
> 目标阶段: 先解决农场现场功能闭环，安全体系后置到小规模试点前

## 1. 目标

当前阶段把云端定义为“农场局域网私有云”，不是公网 SaaS。目标是让一套农场设备在专用 WiFi 内完成:

- 地块创建、分割、机器分配
- 作业创建、下发、取消、重试
- 边侧自动报到、云端发现、人工确认注册
- 任务状态、心跳、进度回传
- 多步骤作业自动推进

核心验收标准是: 云端盒子、路由器、车辆上电后，在同一个局域网内能互相看到并完成任务下发闭环。

## 2. 部署模型

```
┌──────────────── 农场专用 WiFi / LAN ────────────────┐
│                                                       │
│  OpenWrt Router                                      │
│   - Dedicated WiFi / DHCP / local DNS                │
│   - Cloud Box static lease                           │
│   - Optional bootstrap.json                          │
│                                                       │
│  ┌───────────────┐           MQTT / HTTP / SSE        │
│  │ Cloud Box     │◄──────────────────────────────┐    │
│  │ 192.168.10.10 │                               │    │
│  │               │                               │    │
│  │ FastAPI API   │                               │    │
│  │ Vue Web       │                               │    │
│  │ MQTT Broker   │                               │    │
│  │ SQLite DB     │                               │    │
│  └───────┬───────┘                               │    │
│          │                                       │    │
│          │ Optional whitelist egress             │    │
│          ▼                                       │    │
│    Map tiles / NTP / update mirrors              │    │
│                                                  │    │
│  ┌────────────────────┐   ┌────────────────────┐ │    │
│  │ Edge tractor-01    │   │ Edge tractor-02    │ │    │
│  │ Runtime Daemon     │   │ Runtime Daemon     │ │    │
│  │ TaskAgent          │   │ TaskAgent          │ │    │
│  └────────────────────┘   └────────────────────┘ │    │
└──────────────────────────────────────────────────┘
```

### 2.1 Cloud Box

云端盒子运行:

- MQTT broker: 默认 Mosquitto, `1883`
- FastAPI 后端: 默认 `0.0.0.0:8080`
- Vue 前端: 默认 `0.0.0.0:5173`，功能验证阶段先用 Vite dev server
- 数据库: SQLite, 默认 `cloud/server/farm.db`

云端盒子必须使用固定 LAN IP，例如 `192.168.10.10`。这个地址是所有边侧机器的配置锚点。

如果农场路由器使用 OpenWrt，优先在路由器上给 Cloud Box 配置 DHCP 静态租约，并提供本地域名，例如:

- Cloud Box MAC → `192.168.10.10`
- Local DNS → `nodeflow-cloud.lan`

这样边侧可以配置域名而不是裸 IP:

```bash
NF_MQTT_BROKER=nodeflow-cloud.lan
NF_HTTP_SERVER_URL=http://nodeflow-cloud.lan:8080
```

### 2.2 Edge

每台车运行两个常驻服务:

- `nodeflow-runtime.service`: 启动 runtime daemon，监听 `runtime.control`
- `nodeflow-agent.service`: 启动 TaskAgent，连接 MQTT broker，发心跳，接收任务，写入 runtime control buffer

边侧环境配置集中在 `/etc/nodeflow/edge.env`:

```bash
NF_MACHINE_ID=tractor-01
NF_MQTT_BROKER=192.168.10.10
NF_MQTT_PORT=1883
NF_HTTP_SERVER_URL=http://192.168.10.10:8080
NF_TASK_AUTO_ACCEPT=true
NODEFLOW_CONFIG=/opt/nodeflow/examples/tillage_operation.yaml
NODEFLOW_ROOT=/opt/nodeflow
```

注意: 当前 `NF_MQTT_BROKER` 是主机名或 IP，不是 `mqtt://...` URL。

## 3. 发现机制

当前业务发现机制不是局域网扫描，而是边侧主动报到:

1. TaskAgent 启动后读取 `NF_MACHINE_ID` 和 `NF_MQTT_BROKER`
2. TaskAgent 连接 MQTT broker
3. TaskAgent 立即发布一次 heartbeat，之后每 30 秒发布一次
4. 云端订阅 `nodeflow/+/heartbeat`
5. 云端收到未知 `machine_id` 的心跳后，创建 `Machine(status="unregistered")`
6. 操作员在机器看板中确认注册
7. 后续作业可把 split 分配给该 `machine_id`

这个机制适合专用 WiFi 场景: 只要边侧知道 Cloud Box 的固定 IP，就能完成发现，不需要 mDNS、UDP 广播或公网注册服务。

OpenWrt 可以补足“Cloud Box 地址发现/配置发现”，但不替代业务层机器发现:

- 路由器负责网络发现: `nodeflow-cloud.lan` 解析、DHCP、默认网关、出网白名单
- 云端负责业务发现: 机器心跳、`unregistered` 登记、人工确认注册
- 边侧负责主动报到: TaskAgent 连接 MQTT 并周期性心跳

## 4. 任务下发链路

```
Web UI
  │
  ▼
POST /api/v1/jobs/{job_id}/dispatch
  │
  ▼
Dispatcher
  │  生成 EdgeTask + dispatch_id
  ▼
MQTT nodeflow/{machine_id}/task/dispatch (QoS 1)
  │
  ▼
TaskAgent
  │  去重 + ACK
  ▼
TaskExecutor
  │  写 runtime.control
  ▼
Runtime Daemon
  │  注入 node_params + start_dataflow
  ▼
TaskAgent status / heartbeat 回传
  │
  ▼
Cloud MQTTClient 更新 EdgeTask / JobStep / Job
```

边侧只订阅自己的 topic:

- `nodeflow/{machine_id}/task/dispatch`
- `nodeflow/{machine_id}/task/cancel`

云端订阅通配 topic:

- `nodeflow/+/heartbeat`
- `nodeflow/+/status`
- `nodeflow/+/task/ack`

## 5. 当前阶段安全边界

先依赖物理隔离和局域网隔离:

- 农场专用 WiFi，不与办公、家庭网络混用
- Cloud Box 只暴露在 LAN 内
- 路由器固定 Cloud Box IP
- 出网只放白名单，例如地图瓦片、NTP、必要软件源
- MQTT 暂不启用 TLS
- Web/API 暂不做细粒度账号权限

这不是最终生产安全方案，只是功能闭环阶段的约束。进入小规模试点前至少要补:

- 管理端登录口令
- MQTT 用户名密码或设备 token
- API 写操作鉴权
- 配置备份与恢复
- Cloud Box 防火墙规则固化

## 6. 安装入口

### 6.1 云端

云端 LAN 安装脚本负责:

- 写入 `/etc/nodeflow/cloud.env`
- 安装/启动 `nodeflow-cloud-api.service`
- 安装/启动 `nodeflow-cloud-web.service`
- 可选启动系统已有的 `mosquitto.service`

最小配置:

```bash
sudo scripts/install_cloud_lan.sh \
  --root /opt/nodeflow \
  --host 0.0.0.0 \
  --port 8080 \
  --web-port 5173 \
  --mqtt-broker 127.0.0.1 \
  --mqtt-port 1883 \
  --public-base-url http://192.168.10.10:8080
```

### 6.2 边侧

边侧安装脚本负责:

- 写入 `/etc/nodeflow/edge.env`
- 安装/启动 `nodeflow-runtime.service`
- 安装/启动 `nodeflow-agent.service`

最小配置:

```bash
sudo scripts/install_edge_service.sh \
  --root /opt/nodeflow \
  --machine-id tractor-01 \
  --cloud-ip 192.168.10.10 \
  --config /opt/nodeflow/examples/tillage_operation.yaml
```

## 7. 功能优先级

### P0: 当前要补齐

- LAN 私有云设计文档
- Edge systemd 安装脚本
- Cloud LAN systemd 安装脚本
- 机器看板能稳定显示自动发现设备
- 作业下发后 step 能自动推进

### P1: 现场可用性

- OpenWrt 配置方案: Cloud Box 静态租约、本地 DNS、专用 WiFi 网段
- 边侧配置从裸 IP 迁移到 `nodeflow-cloud.lan`
- 可选 OpenWrt bootstrap 文件: `/www/nodeflow/bootstrap.json`
- 前端设置页展示 Cloud Box LAN 地址和边侧安装命令模板
- 任务状态页展示 daemon 是否可用
- MQTT publish/ACK 错误可见化
- Edge 服务健康检查命令
- Cloud Box 数据备份脚本

### P2: 试点前安全

- OpenWrt 出网白名单配置清单
- OpenWrt 防火墙规则固化: MQTT/API/Web 仅 LAN 可访问
- 管理端登录
- MQTT 凭据
- API token
- Cloud Box 防火墙脚本
- 路由器白名单配置清单

### P3: 路由器增强能力

以下能力等软路由实物到位后再评估，不进入当前 P0/P1 实现:

- OpenWrt 托管 `bootstrap.json`，边侧开机从默认网关拉取 Cloud Box 配置
- OpenWrt 上运行 Mosquitto，把 MQTT broker 从 Cloud Box 解耦
- OpenWrt 采集局域网设备列表，用于辅助排障而不是业务注册
- OpenWrt 提供现场维护页，显示 Cloud Box、车辆、外网白名单状态

初期不建议把 MQTT broker 放到路由器上。更稳妥的第一阶段是: OpenWrt 只做专用 WiFi、DHCP、DNS 和白名单；Cloud Box 继续运行 MQTT、API、Web 和数据库。

## 8. 验收流程

1. Cloud Box 接入专用 WiFi，确认固定 IP
2. 安装云端服务，打开 `http://<cloud-ip>:5173`
3. Edge 接入同一 WiFi，安装边侧服务
4. 机器看板出现 `unregistered` 设备
5. 操作员确认注册
6. 创建地块和作业
7. 下发作业
8. EdgeTask 收到 ACK，状态进入 `downloading/ready/running`
9. 任务完成后，多步骤作业自动推进到下一步
10. 最后一步完成后 job 进入 `completed`

## 9. 已知限制

- 云端路径制品已接入 SQLite；大地块规划后续需要迁移到后台作业队列
- SQLite 只适合本地验证，不适合多 worker 并发
- MQTT 还没有凭据和 TLS
- TaskAgent 与 Runtime Daemon 之间使用 latest-value control buffer，不是命令队列
- Edge 服务当前假设 systemd/Linux，macOS 仅用于开发调试
