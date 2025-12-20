# Logger Node

多输入日志记录节点，带实时 Web 展示界面。

## 功能特性

- **3 个输入端口**：接收任意类型的数据（any 类型）
- **实时 Web 展示**：通过 WebSocket 实时推送日志到浏览器
- **内存缓冲**：环形缓冲区，自动覆盖最旧的日志
- **文件日志**：可选的 JSON Lines 格式文件输出
- **过滤和搜索**：支持按端口过滤和关键字搜索
- **日志导出**：一键导出为 JSON 文件

## 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `web_port` | int | 8001 | Web 服务端口号 |
| `buffer_size` | int | 1000 | 内存缓冲区大小（条数） |
| `enable_file_log` | bool | false | 是否启用文件日志输出 |
| `log_file_path` | string | "./logs/logger.jsonl" | 日志文件路径 |

## 使用示例

### 在 runtime.yaml 中配置

```yaml
nodes:
  - id: logger_main
    package: logger
    params:
      web_port: 8001
      buffer_size: 500
      enable_file_log: true
      log_file_path: "./logs/system.jsonl"

edges:
  - from_node: gps_sensor
    from_port: gps_fix
    to_node: logger_main
    to_port: input1

  - from_node: controller
    from_port: control_cmd
    to_node: logger_main
    to_port: input2
```

### 访问 Web 界面

启动节点图后，在浏览器中访问：

```
http://localhost:8001
```

## Web 界面功能

- **实时日志流**：自动推送新日志，无需刷新
- **端口过滤**：点击端口按钮切换显示/隐藏
- **关键字搜索**：在搜索框输入关键字实时过滤
- **导出日志**：点击 Export 按钮下载 JSON 格式日志
- **清空日志**：点击 Clear 按钮清空内存缓冲区

## 日志文件格式

JSON Lines 格式（每行一个 JSON 对象）：

```jsonl
{"timestamp": 1703001234.567, "port": "input1", "data": {"lat": 39.9, "lng": 116.4}}
{"timestamp": 1703001235.678, "port": "input2", "data": {"throttle": 0.5, "steering": 0.1}}
```

## 安装依赖

```bash
cd node-hub/logger
pip install -r requirements.txt
```

## 端口说明

### 输入端口

- **input1** (any)：第一个输入端口
- **input2** (any)：第二个输入端口
- **input3** (any)：第三个输入端口

### 输出端口

无输出端口（终端节点）

## 技术实现

- **双线程架构**：主线程读取输入端口，Web 服务线程处理 HTTP/WebSocket
- **非阻塞读取**：使用 SDK 的 `recv_latest()` 方法
- **环形缓冲**：使用 `collections.deque(maxlen=N)`
- **线程安全**：使用 `threading.Lock` 保护缓冲区
- **WebSocket 推送**：FastAPI + WebSocket 实时数据流

## 性能特性

- **读取频率**：100Hz（主循环 10ms 间隔）
- **内存占用**：取决于 buffer_size 和数据大小
- **CPU 使用**：低 CPU 占用，非阻塞 I/O
- **WebSocket 并发**：支持多个浏览器同时连接

## 故障排查

### 端口占用

如果端口 8001 被占用，修改 `web_port` 参数：

```yaml
params:
  web_port: 8080  # 使用其他端口
```

### 无法连接 WebSocket

检查防火墙设置，确保端口可访问：

```bash
# macOS
lsof -i :8001

# Linux
netstat -tuln | grep 8001
```

### 日志文件写入失败

确保日志目录存在且有写权限：

```bash
mkdir -p ./logs
chmod 755 ./logs
```

## 扩展建议

后续可以添加的功能：

1. **高级过滤**：支持正则表达式、时间范围过滤
2. **性能监控**：显示消息速率、延迟统计
3. **日志归档**：自动按日期或大小切分日志文件
4. **多格式导出**：支持 CSV、Excel 等格式
5. **图表展示**：数据可视化图表
