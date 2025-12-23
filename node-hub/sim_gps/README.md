# sim_gps - 仿真 GPS 节点

仿真 GPS 节点，从 NodeFlow 仿真器读取机器人位置数据，生成 GPS 坐标。

## 功能

- ✅ 从仿真器实时读取机器人位置
- ✅ 转换为经纬度和海拔数据
- ✅ 模拟 GPS 噪声
- ✅ 发布标准的 GPS fix 消息

## 输出数据

**端口**: `gps_fix` (JSON)

```json
{
  "latitude": 40.712840,
  "longitude": -74.005958,
  "altitude": 10.5,
  "hdop": 0.85,
  "fix_quality": 4,
  "num_satellites": 12,
  "timestamp": 1234567890.123
}
```

**字段说明**:
- `latitude`: 纬度 (度)，范围 [-90, 90]
- `longitude`: 经度 (度)，范围 [-180, 180]
- `altitude`: 海拔高度 (米)
- `hdop`: 水平精度因子 (HDOP)，值越小精度越高
- `fix_quality`: 定位质量
  - 0: 无定位
  - 1: GPS fix
  - 2: DGPS fix
  - 4: RTK Fixed (最高精度)
- `num_satellites`: 使用的卫星数量
- `timestamp`: 仿真时间戳

## 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `simulator_host` | string | localhost | 仿真器服务器地址 |
| `simulator_port` | integer | 5555 | 仿真器服务器端口 |
| `frequency` | integer | 10 | 数据发布频率 (Hz) |
| `timeout` | integer | 1000 | ZMQ 请求超时 (毫秒) |

## 使用示例

### 场景配置

```yaml
nodes:
  - name: sim_gps
    package: sim_gps
    params:
      simulator_host: localhost
      simulator_port: 5555
      frequency: 10      # 10Hz GPS 更新率

edges: []              # 本节点为数据源，无输入边
```

### 连接到其他节点

```yaml
edges:
  - {from_node: sim_gps, from_port: gps_fix, to_node: sensor_fusion, to_port: gps_in}
  - {from_node: sim_gps, from_port: gps_fix, to_node: localization, to_port: gps_input}
```

## 常见问题

### Q: 连接仿真器失败

**症状**: `ZMQ 请求超时` 或 `Connection refused`

**原因**: 仿真器服务器未启动或地址/端口错误

**解决**:
```bash
# 1. 确保仿真器在运行
python3 simulator/server.py --port 5555

# 2. 检查参数配置
# - simulator_host 是否正确
# - simulator_port 是否与仿真器一致

# 3. 检查网络连接
telnet localhost 5555
```

### Q: GPS 数据不更新

**症状**: 接收到数据但位置始终不变

**原因**: 可能仿真器中的机器人未运动

**解决**: 检查是否有控制节点（如 sim_motor）在向仿真器发送动作指令

### Q: 数据精度信息

GPS 数据精度由仿真器的 `gps_noise_std` 参数控制：
- 默认 0.5 米误差标准差
- HDOP 根据噪声自动计算

实际场景中 GPS 精度会更差，可在仿真器配置中调整。

## 性能指标

- **发布延迟**: < 1ms (本地 ZMQ)
- **数据频率**: 可达 100+ Hz
- **CPU 占用**: < 1%
- **内存占用**: 5 MB

## 相关节点

- **sim_imu**: 仿真惯性测量单元 (IMU)
- **sim_motor**: 仿真电机控制执行器
- **sensor_fusion**: 传感器数据融合
- **localization**: 定位算法节点

## 维护者

NodeFlow 团队
