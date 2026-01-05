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
- **近实时推送**: 每次接收到新数据后 0.1 秒内推送到浏览器（防抖机制）
- **WebSocket 双向通信**: 数据更新自动推送到所有连接的浏览器
- **交互式图表**: 使用 Plotly.js，支持缩放、平移、悬停查看数据
- **响应式设计**: 自动适配不同屏幕尺寸

### 📊 可视化内容
- **地块边界**: 绿色半透明多边形
- **规划路径**: 蓝色线条 + 起点/终点标记
- **实际轨迹**: 红色线条 + 起点/终点标记
- **航向角箭头**: 红色箭头显示机器人朝向（每 20 个点显示一个）
- **实时统计**: 距离误差、横向误差、轨迹点数等指标

### 🔧 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `web_host` | string | `"0.0.0.0"` | Web 服务器监听地址 |
| `web_port` | int | `5000` | Web 服务器端口号 |
| `update_interval` | float | `5.0` | 日志打印间隔（秒）*，不影响数据推送频率 |
| `timeout` | float | `300.0` | 节点超时时间（秒） |

*注：数据推送是**近实时的**（0.1秒防抖），`update_interval` 仅控制控制台日志打印频率，避免刷屏。

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

## 实时更新机制

### 工作原理

```
接收到新数据（pose_enu、task_enu、global_path）
    ↓
设置 data_changed = true
    ↓
主循环检测到数据变化
    ↓
防抖检查（距上次推送 >= 0.1 秒）
    ↓
计算指标 + WebSocket 推送
    ↓
浏览器接收数据并更新图表（Plotly.react）
```

### 关键特性

1. **事件驱动**: 只有当数据真正变化时才推送，避免无效计算
2. **防抖机制**: 0.1 秒的最小推送间隔，避免过载同时保持��畅
3. **非阻塞**: 推送操作在主循环中，不影响数据接收
4. **平滑更新**: 前端使用 `Plotly.react()` 增量更新，无闪烁

### 性能指标

- **延迟**: < 0.1 秒（从接收数据到浏览器显示）
- **推送频率**: 最高 10 Hz（每秒 10 次）
- **CPU 占用**: 主循环 sleep(0.1) 控制在 < 5%


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

### v2.0.2 (2026-01-06)
- ✨ **新增**: 航向角箭头显示（红色箭头，显示机器人朝向）
- 🐛 **修复**: 补充遗漏的航向角可视化功能
- 📝 **文档**: 更新可视化内容说明

### v2.0.1 (2026-01-06)
- 🚀 **性能提升**: 实现真正的近实时更新（0.1秒防抖）
- ✨ **优化**: 事件驱动推送机制，只在数据变化时推送
- 🐛 **修复**: 解决"10秒一跳"的问题，现在是平滑实时更新
- 📝 **文档**: 更新参数说明，澄清 `update_interval` 的作用

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
