# 轨迹实时可视化节点（Web 版本）

## 概述

轨迹实时可视化节点提供 **基于 Web 的实时可视化界面**，通过浏览器实时查看农业机器人的规划路径和实际轨迹对比。

**技术栈：**
- **后端**: Flask + WebSocket (Flask-SocketIO)
- **前端**: Plotly.js (交互式图表库)
- **通信**: WebSocket 实时数据推送

## 快速开始

### 1. 安装依赖

```bash
cd node-hub/trajectory_viz
pip3 install -r requirements.txt
```

依赖包：
- `flask>=2.3.0` - Web 框架
- `flask-socketio>=5.3.0` - WebSocket 支持
- `python-socketio>=5.9.0` - SocketIO 客户端/服务器
- `numpy>=1.20.0` - 数值计算

### 2. 运行测试

```bash
python3 test_web.py
```

然后在浏览器中打开: http://localhost:5000

### 3. 在工作流中使用

配置文件示例 (例如 `planning_simulation.yaml`):

```yaml
nodes:
  - id: trajectory_viz
    package: trajectory_viz
    params:
      web_port: 5000          # Web 服务器端口
      web_host: "0.0.0.0"     # 监听地址（0.0.0.0 表示所有网络接口）
      update_interval: 5.0    # 每 5 秒推送一次数据到浏览器
      timeout: 600.0          # 10 分钟后自动关闭

edges:
  # 连接地块边界数据
  - from_node: sim_output
    from_port: task_enu
    to_node: trajectory_viz
    to_port: task_enu

  # 连接规划路径数据
  - from_node: global_coverage
    from_port: global_path
    to_node: trajectory_viz
    to_port: global_path

  # 连接实际轨迹数据
  - from_node: sim_output
    from_port: pose_enu
    to_node: trajectory_viz
    to_port: pose_enu
```

启动后，在浏览器中访问: `http://localhost:5000` (或者 `http://<机器IP>:5000`)

## 功能特性

### ✨ 实时可视化
- **WebSocket 实时推送**: 数据更新自动推送到所有连接的浏览器
- **交互式图表**: 使用 Plotly.js，支持缩放、平移、悬停查看数据
- **响应式设计**: 自动适配不同屏幕尺寸

### 📊 可视化内容
- **地块边界**: 绿色半透明多边形
- **规划路径**: 蓝色线条 + 起点/终点标记
- **实际轨迹**: 红色线条 + 起点/终点标记
- **实时统计**: 距离误差、横向误差、轨迹点数等指标

### 🔧 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `web_host` | string | `"0.0.0.0"` | Web 服务器监听地址 |
| `web_port` | int | `5000` | Web 服务器端口号 |
| `update_interval` | float | `5.0` | 数据推送间隔（秒） |
| `timeout` | float | `300.0` | 节点超时时间（秒） |

## 输入/输出

### 输入端口

| 端口名 | 数据类型 | 说明 |
|--------|----------|------|
| `task_enu` | `planning.task_enu` | 规划任务（包含地块边界、GPS 参考点）|
| `global_path` | `planning.path` | 规划器输出的全局路径（ENU 坐标）|
| `pose_enu` | `localization.pose_enu` | ENU 坐标系姿态（实际轨迹点）|

### 输出端口

| 端口名 | 数据类型 | 说明 |
|--------|----------|------|
| `web_url` | `json` | Web 界面 URL 和统计信息 |

输出数据格式：
```json
{
  "url": "http://0.0.0.0:5000",
  "timestamp": "2026-01-05T12:34:56",
  "update_count": 10,
  "stats": {
    "planned_distance_m": 280.0,
    "actual_distance_m": 275.5,
    "distance_error_m": 4.5,
    "distance_error_percent": 1.6,
    "avg_lateral_error_m": 1.2,
    "max_lateral_error_m": 2.5,
    "trajectory_points": 150
  }
}
```

## 使用场景

### 1. 实时监控
在作业过程中实时查看轨迹跟踪质量，及时发现问题。

### 2. 远程调试
通过局域网访问可视化界面，无需在现场查看。

### 3. 多客户端同时查看
支持多个浏览器同时连接，团队成员可同时监控。

### 4. 开发调试
快速验证路径规划和控制算法效果。

## 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                     NodeFlow 节点                            │
│                                                               │
│  ┌──────────────┐                                            │
│  │   run.py     │  接收数据流                                │
│  │              │  ↓                                         │
│  │  TrajectoryViz│  task_enu, global_path, pose_enu        │
│  │     Node     │  ↓                                         │
│  │              │  计算指标 (atom.py)                        │
│  └──────┬───────┘  ↓                                         │
│         │          update_trajectory_data()                  │
│         ↓                                                     │
│  ┌──────────────────────────────────┐                        │
│  │      web_server.py               │                        │
│  │  ┌────────────────────────────┐  │                        │
│  │  │  Flask App                 │  │                        │
│  │  │  - HTTP Server (/)         │  │                        │
│  │  │  - WebSocket Handler       │  │                        │
│  │  └────────────────────────────┘  │                        │
│  └──────────────┬───────────────────┘                        │
│                 │ WebSocket 推送                              │
└─────────────────┼─────────────────────────────────────────┘
                  │
                  ↓
         ┌────────────────┐
         │   浏览器客户端   │
         │                │
         │  - Plotly.js   │
         │  - Socket.IO   │
         │  - 实时更新图表 │
         └────────────────┘
```

## 与旧版本对比

| 特性 | 旧版本（v1.0） | 新版本（v2.0 Web） |
|------|----------------|-------------------|
| 可视化方式 | 静态 JPG/PNG 图像 | Web 实时可视化 |
| 更新方式 | 定期生成新图像文件 | WebSocket 实时推送 |
| 查看方式 | 打开图像文件 | 浏览器访问 |
| 交互性 | 无 | 支持缩放、平移、悬停 |
| 多用户 | 需要共享文件 | 支持多浏览器同时访问 |
| 依赖 | matplotlib | Flask + Plotly.js |
| 磁盘占用 | 每次更新生成新文件 | 无磁盘占用 |

## 故障排查

### 1. 浏览器无法访问

**问题**: 浏览器显示"无法连接"

**解决方案**:
- 检查节点是否正常启动
- 检查防火墙设置，确保端口 5000 开放
- 尝试使用 `http://127.0.0.1:5000` 替代 `localhost`

### 2. 页面显示"连接已断开"

**问题**: 页面加载但显示红色断开状态

**解决方案**:
- 检查节点日志，确认 Web 服务器是否正常运行
- 检查是否有防火墙阻止 WebSocket 连接
- 刷新浏览器页面重新连接

### 3. 数据不更新

**问题**: 页面正常但轨迹数据不显示

**解决方案**:
- 检查数据流是否正确连接（查看节点日志）
- 确认 `update_interval` 参数设置合理
- 检查输入数据格式是否正确

### 4. 端口冲突

**问题**: 启动失败，提示"Address already in use"

**解决方案**:
- 修改 `web_port` 参数使用其他端口（如 5001, 8000）
- 或者终止占用端口 5000 的其他进程

## 开发指南

### 添加新的可视化元素

编辑 `web_server.py` 中的 HTML 模板，在 `socket.on('trajectory_update')` 回调中添加新的 Plotly trace。

### 修改样式

修改 `web_server.py` 中的 CSS 样式部分。

### 自定义统计指标

修改 `atom.py` 中的 `calculate_trajectory_metrics()` 函数。

## 版本历史

### v2.0.0 (2026-01-05)
- 🎉 **重大更新**: 从静态图像改为 Web 实时可视化
- ✨ 使用 Flask + WebSocket 实现实时数据推送
- ✨ 使用 Plotly.js 实现交互式图表
- ✨ 支持多浏览器同时访问
- ♻️ 移除 matplotlib 依赖
- ♻️ 简化配置参数

### v1.0.0 (2025-12-24)
- 🎉 初始版本：基于 matplotlib 的静态图像生成

## 许可证

GPL-3.0

## 贡献

欢迎提交 Issue 和 Pull Request！
