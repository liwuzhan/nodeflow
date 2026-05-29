# NodeFlow 实机测试计划

> 日期: 2026-05-01  
> 硬件: 履带底盘 + UM982 RTK + Orange Pi 5 Ultra  
> 软件: NodeFlow 云端 + 边侧 (master 分支)

---

## 1. 测试目标

验证 NodeFlow 从**云端任务下发 → 边侧接收 → 节点启动 → 自主作业**的完整链路在真实硬件上可用。

分三层递进：
| 层级 | 目标 | 不依赖 |
|------|------|--------|
| L0 基础验证 | RTK 定位正常、PWM 控制正常、手柄/Web 遥控 | 云端 |
| L1 单机自主 | 预设路径跟踪、地块规划→自主作业 | 云端 |
| L2 云端联动 | MQTT 下发任务 → 自动执行 → 状态上报 | — |

### 1.1 版本冻结

实机测试不要只写“master 分支”，建议在出发前冻结版本并记录:

```bash
# 笔记本
cd ~/nodeflow
git rev-parse HEAD

# Orange Pi
cd ~/nodeflow
git rev-parse HEAD
```

记录项:

- 笔记本提交号
- Orange Pi 提交号
- 实际使用的 YAML 文件路径
- 实际修改过的参数（串口、PWM、gain、dry_run 等）

**要求**: 笔记本和 Orange Pi 使用同一提交，现场临时改 YAML 时要把最终版本单独备份。

---

## 2. 硬件清单

### 车上已有

| 设备 | 型号/规格 | 备注 |
|------|----------|------|
| 底盘 | 履带式 | 差速转向 |
| 电机驱动 | PWM 调速器 | 50Hz, 1-2ms 脉宽 |
| GNSS | UM982 | 双天线 RTK |
| 4G 模块 | Air700E | UM982 ↔ USB 桥接，含 5s 看门狗 |
| 计算平台 | Orange Pi 5 Ultra | Linux, sysfs PWM |
| 天线 | 双 GNSS 天线 | 已装车 |

### 需带到现场

| 物品 | 数量 | 用途 |
|------|------|------|
| 笔记本电脑 | 1 | 运行云端 + SSH 到 Orange Pi |
| 移动电源 / 逆变器 | 1 | 给 Orange Pi + 路由器供电 |
| 便携路由器 | 1 | 局域网 (MQTT broker + API) |
| 网线 | 2 | 笔记本↔路由器, Pi↔路由器 |
| 卷尺 (20m+) | 1 | 标定测量 |
| 角锥 / 标志物 | 4+ | 地块顶点标记 |
| RTK 基站 | 1 | 差分信号（如无网络 CORS） |
| 急停开关 | 1 | **安全必备** |
| 对讲机 | 2 | 车上/场边通信 |

---

## 3. 软件部署

### 3.1 Orange Pi (边侧)

```bash
# 1. 确认环境
python3 --version  # 需要 3.12+
cd ~/nodeflow
git pull origin master

# 2. 安装依赖
pip install -r requirements.txt
pip install paho-mqtt

# 3. 检查串口
ls /dev/ttyUSB* /dev/ttyACM*
# 预期: /dev/ttyACM3 (UM982 通过 Air700E)

# 4. 停掉 ModemManager (会占用串口)
sudo systemctl stop ModemManager

# 5. 验证 RTK 数据
python3 node-hub/rtk_driver/test_serial.py
# 预期: 持续收到 $GNGGA, $GNTHS, $GNRMC

# 6. 验证 PWM
python3 -c "
from node_hub.pwm_driver.atom import PWMController
# dry_run 模式验证 sysfs 可访问
"
```

### 3.2 笔记本电脑 (云端)

```bash
cd ~/nodeflow
git pull origin master

# 安装依赖
cd cloud/server && pip install -r requirements.txt
cd ../web && npm install

# 确认 mosquitto
which mosquitto

# 确认前端可启动（如需用 Web UI）
cd ../web
npm run dev
# 预期: http://localhost:5173
```

### 3.3 网络拓扑

```
        ┌─────────────┐
        │ 便携路由器    │  192.168.1.x/24
        │ (MQTT broker) │
        └──┬───────┬──┘
           │       │
    ┌──────┘       └──────┐
    ▼                     ▼
┌─────────┐         ┌──────────┐
│ 笔记本    │         │ Orange Pi │
│ 192.168.1.100     │ 192.168.1.101
│                    │
│ 云端 server :8080  │ 边侧 daemon + agent
│ mosquitto :1883   │ NF_MQTT_BROKER=192.168.1.100
└─────────┘         └──────────┘
```

### 3.4 联调前连通性检查

在开始任何 L1/L2 测试前，必须先做以下检查:

```bash
# 笔记本 → Orange Pi
ping 192.168.1.101

# Orange Pi → 笔记本
ping 192.168.1.100

# 笔记本检查云端 API
curl http://localhost:8080/api/v1/health

# Orange Pi 检查 MQTT 端口
nc -vz 192.168.1.100 1883
```

通过标准:

- 笔记本与 Orange Pi 双向可 ping 通
- `GET /api/v1/health` 返回 `{"status":"ok"}`
- MQTT `1883` 端口可连接

### 3.5 真机联调推荐启动顺序

**不要** 在 L2 真机联调时直接使用:

```bash
python3 tests/e2e_cli.py start
```

原因:

- 该脚本会在笔记本本地同时启动 `cloud + daemon + agent`
- 会和 Orange Pi 上的真实边侧角色冲突

真机联调建议按以下顺序手工启动。

#### 笔记本

```bash
# 1. 启动 MQTT broker
mosquitto -p 1883

# 2. 启动云端 API
cd ~/nodeflow
PYTHONPATH=$PWD python3 -m uvicorn cloud.server.app:app --host 0.0.0.0 --port 8080

# 3. 可选：启动前端
cd ~/nodeflow/cloud/web
npm run dev
```

#### Orange Pi

```bash
# 1. 启动 daemon
cd ~/nodeflow
python3 -m runtime.main examples/tillage_operation.yaml --daemon

# 2. 启动 TaskAgent
NF_MACHINE_ID=tractor-01 \
NF_MQTT_BROKER=192.168.1.100 \
NF_MQTT_PORT=1883 \
python3 -m runtime.task.agent_main
```

#### 启动后立即检查

- 笔记本: `curl http://localhost:8080/api/v1/health`
- 云端 UI: `http://localhost:5173`
- Orange Pi: agent 日志中看到 MQTT connected / subscribed
- daemon 日志中看到 `Control buffer ready: runtime.control`

---

## 4. 安全规程

### 4.1 急停机制（三层）

| 层级 | 触发方式 | 效果 |
|------|----------|------|
| **物理** | 急停开关 (硬件断电) | 电机立即停转 |
| **软件** | `pwm_driver.emergency_stop=true` | PWM 输出 center 脉宽 |
| **超时** | `command_timeout: 0.5s` | 无指令 0.5s 后自动停 |

### 4.2 测试前安全检查

- [ ] 急停开关功能正常（按下后电机不能转）
- [ ] `dry_run_mode: true` 初次测试（PWM 不输出，仅计算）
- [ ] 底盘悬空 或 空旷区域（半径 20m 内无人/障碍物）
- [ ] 所有人员站在底盘后方或侧方，不站在前进方向
- [ ] 对讲机通信确认

### 4.3 速度递增策略

```
阶段 0: dry_run_mode=true     → 仅数据, 不动
阶段 1: duty_scale=0.3  max_speed=0.3  → 慢速验证
阶段 2: duty_scale=0.5  max_speed=0.5  → 半速
阶段 3: duty_scale=0.8  max_speed=1.0  → 作业速度
阶段 4: duty_scale=1.0  max_speed=2.0  → 全速 (仅在空旷区域)
```

**每阶段通过后才进入下一阶段。任意阶段出现异常立即急停。**

### 4.4 禁止事项

- **禁止** 取消 GGA/RMC 消息（UM982 Air700E 看门狗 5s 超时重启）
- **禁止** 在 `dry_run_mode: false` 时首先全速测试
- **禁止** 人站在底盘正前方 5m 内
- **禁止** 无对讲机通信时启动自主模式

### 4.5 收车 / 回退流程

每轮测试结束后，必须执行统一回退流程:

1. 操作员口头确认: “停止测试，车辆归零”
2. 在云端或边侧停止当前作业
3. 确认 PWM 回中位，底盘不再响应旧命令
4. 确认 daemon 不再处于 `dataflow_running=true`
5. 如需重启下一轮，先清空旧日志和旧 PID，再重新启动

建议命令:

```bash
# Orange Pi - 停止 agent
pkill -f runtime.task.agent_main || true

# Orange Pi - 停止 daemon
pkill -f "runtime.main .* --daemon" || true

# 确认 runtime 相关进程已退出
ps aux | grep runtime.main
ps aux | grep runtime.task.agent_main
```

**要求**: 未完成收车确认，不进入下一轮测试。

### 4.6 现场口令

建议固定使用以下口令，避免多人配合时误操作:

- “准备启动”
- “开始移动”
- “急停”
- “解除急停”
- “进入下一阶段”
- “本轮结束，车辆归零”

---

## 5. 测试场景

### 5.0 进入 L1 / L2 前的静态核对清单

- [ ] 笔记本与 Orange Pi 提交号一致
- [ ] `serial_port` 与现场实际设备一致（不要假设一定是 `/dev/ttyACM3`）
- [ ] `dry_run_mode` 已按当前阶段设置正确
- [ ] `NF_MQTT_BROKER` / `NF_MQTT_PORT` / `NF_MACHINE_ID` 已确认
- [ ] 地块 JSON 已更新为现场使用版本
- [ ] 天线偏移、参考点、wheel_base 已记录当前值
- [ ] 云端 API / MQTT / 前端页面均可访问

**任何一项未确认，不进入 L1 / L2。**

### L0-1: Web 遥控验证

**目的**: 确认 PWM 输出正确，底盘可手动控制  
**配置**: `examples/web_pwm_teleop.yaml`  
**步骤**:
1. 底盘悬空 / 空旷区
2. 首次上电先确认 `dry_run_mode: true`，验证链路和网页可访问
3. 确认无异常后，再切到 `dry_run_mode: false`
4. 启动: `python3 -m runtime.main examples/web_pwm_teleop.yaml`
5. 浏览器打开 `http://<Pi_IP>:9873`
6. W/S 前进/后退、A/D 左转/右转、空格停止
7. 验证: 电机方向正确、左右匹配

**通过标准**: W=前进 A=左转 D=右转 S=后退 空格=停

---

### L0-2: RTK 定位验证

**目的**: 确认 UM982 输出正确，RTK FIX 可获得  
**步骤**:
1. 将 RTK 基站架设在空旷处，记录基站坐标
2. 移动端 UM982 开机，等待 RTK FIX（通常 30s-2min）
3. 先做串口/NMEA 验证:
   ```bash
   python3 node-hub/rtk_driver/test_serial.py
   ```
4. 如需走 NodeFlow 实际链路，使用现有配置:
   ```bash
   python3 -m runtime.main examples/planning_with_real_rtk.yaml
   ```
5. 观察日志: `rtk_quality=3 (FIXED), satellites>=10`
6. 手持天线在已知两点间移动（如 10m），验证坐标变化量

**注意**:

- 当前仓库中没有 `examples/rtk_test.yaml`
- 现场不要按旧文档引用不存在的配置文件执行

**通过标准**: 持续 RTK FIX，10m 直线测量误差 < 10cm

---

### L0-3: 直线跟踪验证

**目的**: 验证定位→控制→PWM 闭环，底盘可走直线  
**配置**: `examples/planning_with_real_rtk.yaml`  
**修改**: `dry_run_mode: false`, `duty_scale: 0.3`, `max_speed: 0.3`  
**步骤**:
1. 在地面标记 10m 直线起点/终点
2. 将底盘置于起点，车头对准终点
3. 创建单条直线路径（手工录入坐标）
4. 启动数据流，观察底盘沿直线前进
5. 到达终点后自动停止 (final_stop_distance=0.5m)

**通过标准**:
- 底盘沿直线行进，无明显蛇形
- 到达终点 ±0.5m 内自动停止
- 全程 RTK quality 保持 FIXED

---

### L1-1: 地块规划→自主作业

**目的**: 完整规划→跟踪→作业流程  
**配置**: `examples/tillage_operation.yaml`（修改为真机参数）  
**步骤**:
1. 用 GPS/手机 采集地块 4 个角点坐标，写入 `parcels/default.json`
2. 将底盘置于地块起点位置
3. 启动数据流，观察 global_coverage 规划路径
4. 底盘沿覆盖路径自主行驶

**通过标准**:
- global_coverage 生成合理覆盖路径
- 底盘按路径自动行驶
- 地头处正确转弯
- 覆盖面积 > 预估面积的 90%

---

### L2-1: 云端下发任务

**目的**: 验证 MQTT 下发 → 边侧接收 → 自动执行  
**步骤**:
1. 笔记本启动云端服务（不要用 `tests/e2e_cli.py start`）:
   ```bash
   # MQTT broker
   mosquitto -p 1883

   # Cloud API
   cd ~/nodeflow
   PYTHONPATH=$PWD python3 -m uvicorn cloud.server.app:app --host 0.0.0.0 --port 8080

   # 可选: Web UI
   cd cloud/web && npm run dev
   ```
2. Orange Pi 启动 daemon + agent:
   ```bash
   python3 -m runtime.main examples/tillage_operation.yaml --daemon &
   NF_MACHINE_ID=tractor-01 NF_MQTT_BROKER=192.168.1.100 \
     python3 -m runtime.task.agent_main &
   ```
3. 笔记本先创建 Job，再执行 dispatch:
   ```bash
   # 方式 A: Web UI
   # http://localhost:5173

   # 方式 B: API
   # 先 POST /api/v1/parcels
   # 再 POST /api/v1/jobs
   # 最后 POST /api/v1/jobs/{id}/dispatch
   ```
4. 按以下门禁逐段确认:
   - 云端看到 job / edge_task 创建成功
   - agent 收到 `task_dispatch` 并发送 ACK
   - daemon 日志中出现 `Received command: start_dataflow`
   - dataflow 启动成功
   - 底盘开始移动
5. 若任一门禁失败，立即停止当前轮并记录失败层级

**通过标准（必须全部满足）**:

- 云端 job 状态进入 `running`
- agent 成功 ACK
- daemon 成功收到并执行 `start_dataflow`
- 底盘开始移动，无需人工 SSH 到 Pi 手动启动数据流
- 云端可看到后续状态更新

**失败分层记录**:

- F1 云端未创建任务
- F2 MQTT 未送达 / agent 未 ACK
- F3 agent 收到但 daemon 未启动
- F4 daemon 已启动但底盘未运动
- F5 底盘已运动但状态上报异常

**不要使用**:

```bash
python3 tests/e2e_cli.py start
```

该命令适合集成测试，不适合真机 L2 联调。

---

## 6. 参数标定

### 6.1 天线偏移

在 `rtk_driver` 配置中:
```yaml
antenna_offset_x: ?  # 主天线相对车辆中心的纵向偏移 (m, 前+)
antenna_offset_y: ?  # 主天线相对车辆中心的横向偏移 (m, 右+)
heading_offset_deg: ? # 天线指向 ↔ 车头方向的夹角
```

测量方法: 卷尺量天线在车身上的位置。

### 6.2 电机标定

**直线跑偏纠正**:
1. `max_speed=0.3`, 跑 20m 直线
2. 测量横向偏差 d (右偏为正)
3. 调整: `angular_velocity_bias = -d / 20 * 0.3 / wheel_base`
4. 重复直到偏差 < 0.2m

**原地旋转标定**:
1. `v=0, w=0.3`, 计时转一圈
2. 调整 `wheel_base` := `wheel_base * (实际时间 / 理论时间)`
3. 理论时间 = `2π / 0.3 ≈ 20.9s`

### 6.3 track_controller 增益标定

**直线跟踪**: 手动遥控跑 20m，录制轨迹 → `trajectory_playback.yaml` 回放 → 调整 `heading_p_gain`:
- 蛇形振荡过大 → 减小 gain
- 纠偏太慢、偏离预期航向 → 增大 gain

**转弯性能**: 地头转弯时观察:
- 转弯半径过大、切角不锐 → 增大 `max_angular_velocity` 或 `pivot_threshold_deg`

---

## 7. 常见问题排查

### 7.0 现场观察点

建议现场同时盯以下 5 个观察点:

1. **云端 API**: `curl http://localhost:8080/api/v1/health`
2. **Web UI**: 作业详情页是否出现 task / 状态变化
3. **agent 日志**: 是否收到 `task_dispatch` / `task_cancel`
4. **daemon 日志**: 是否收到 `start_dataflow` / `stop_dataflow`
5. **RTK 原始日志**: `/tmp/rtk_raw.log`

如果失败，先判断卡在哪一层，再继续排查，不要同时改多项配置。

| 症状 | 可能原因 | 排查 |
|------|----------|------|
| 无 RTK 数据 | USB 口不对 / ModemManager 占用 | `ls /dev/tty*`, `sudo systemctl stop ModemManager` |
| RTK 始终 FLOAT | 基站距离太远 / 遮挡 | 检查基线距离 (<10km), 天线对天无遮挡 |
| 底盘不动 | `dry_run_mode: true` / PWM 口不对 | 检查配置, `ls /sys/class/pwm/` |
| 底盘反向 | 电机线接反 | 交换 `pwm_min_ns` ↔ `pwm_max_ns` |
| PWM 报错 | sysfs 未 export | `echo 0 > /sys/class/pwm/pwmchip0/export` |
| 底盘蛇形 | P gain 太大 / 天线偏移不准 | 减小 heading_p_gain, 检查 antenna_offset |
| UM982 不断重启 | GGA/RMC 消息被停 | 检查 nmea_message 配置, 不要 UNLOG |
| agent 不连 MQTT | broker IP 不对 / 防火墙 | `ping 192.168.1.100`, 检查 `NF_MQTT_BROKER` |

---

## 8. 人手需求

| 角色 | 人数 | 职责 |
|------|------|------|
| **操作员** | 1 | 笔记本电脑操作 (云端 UI + SSH), 下发指令 |
| **安全员** | 1 | 手持急停开关，监控底盘运动，通信对讲 |
| **测量员** | 0-1 | GPS 采点、卷尺测量、地面标记（可兼） |

**最少 2 人**：操作员 + 安全员。测量工作可由操作员在底盘就位后完成。

---

## 9. 测试日程（预计 1 天）

| 时段 | 内容 | 预计耗时 |
|------|------|----------|
| 09:00-09:30 | 现场部署：路由器供电、Pi 上电、天线架设 | 30min |
| 09:30-10:00 | L0-1: Web 遥控验证 | 30min |
| 10:00-10:30 | L0-2: RTK 定位验证 | 30min |
| 10:30-11:00 | 参数标定 (天线 + 电机) | 30min |
| 11:00-11:30 | L0-3: 直线跟踪验证 | 30min |
| 11:30-12:00 | track_controller 增益调整 | 30min |
| 12:00-13:00 | 午餐 | 60min |
| 13:00-13:30 | L1-1: 地块规划→自主作业 (慢速) | 30min |
| 13:30-14:30 | L1-1: 加速测试、覆盖度验证 | 60min |
| 14:30-15:00 | L2-1: 云端下发 | 30min |
| 15:00-16:00 | 异常场景测试: 通信中断、RTK 失锁、急停恢复 | 60min |
| 16:00-16:30 | 数据收集、轨迹回看、日志归档 | 30min |

---

## 10. 数据记录

### 每条测试记录

```
测试编号: L0-1 / L1-1 / ...
时间:
天气:
RTK状态 (FIX/FLOAT/satellites):
配置参数 (max_speed/duty_scale/gain):
通过/失败:
现象描述:
轨迹截图路径:
原始日志路径: /tmp/rtk_raw.log / /tmp/nodeflow/logs/
```

### 归档

测试结束后将以下文件打包：
- `/tmp/rtk_raw.log`
- `/tmp/nodeflow/logs/*.jsonl`
- `/tmp/rtk_trajectory/trajectory_*.png`
- 现场照片 (底盘、场地、天线架设)
- 标定参数最终值

---

## 11. 快速启动脚本

```bash
#!/bin/bash
# field_test_start.sh — 一键启动边侧所有服务

set -euo pipefail

MACHINE_ID=${1:-tractor-01}
BROKER_IP=${2:-192.168.1.100}
CONFIG=${3:-examples/planning_with_real_rtk.yaml}

echo "=== NodeFlow Field Test ==="
echo "Machine: $MACHINE_ID"
echo "Broker:  $BROKER_IP"
echo "Config:  $CONFIG"

# 停 ModemManager
sudo systemctl stop ModemManager 2>/dev/null

# 检查串口
echo "Serial ports:"
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null

# 检查 broker
echo "Checking broker..."
nc -vz "$BROKER_IP" 1883

# 启动 daemon
python3 -m runtime.main "$CONFIG" --daemon &
sleep 3

# 启动 TaskAgent
NF_MACHINE_ID="$MACHINE_ID" NF_MQTT_BROKER="$BROKER_IP" \
  python3 -m runtime.task.agent_main &

echo "=== Ready ==="
echo "Daemon PID: $(cat /tmp/nodeflow_runtime.pid)"
echo "Agent PID: $!"
echo "Monitor:  tail -f /tmp/nodeflow/logs/*.jsonl"
echo "RTK log:  tail -f /tmp/rtk_raw.log"
```
