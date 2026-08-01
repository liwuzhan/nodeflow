# Position Recorder 节点

位置记录节点 - 手动/自动记录设备当前位置

## 功能说明

- **RTK 数据接收**: 接收 RTK 驱动节点的定位数据
- **手动记录**: 通过 Web 界面点击按钮手动记录当前位置
- **自动记录**: 支持按设定间隔自动记录位置点
- **文件导出**: 记录可导出为 CSV 或 JSON 格式
- **自动清理**: 自动保留最近 N 次记录，删除旧文件

## 节点架构

```
position_recorder/
├── node.yaml          # 节点声明文件
├── run.py             # L3层主逻辑
├── atom.py            # L4层纯算法
├── web_server.py      # Web服务器
├── templates/         # HTML模板
│   └── index.html
├── static/            # 静态资源
│   ├── css/style.css
│   └── js/app.js
├── data/records/      # 记录文件存储目录
└── README.md          # 本文档
```

## 端口说明

### 输入端口

| 端口名 | 类型 | 说明 |
|--------|------|------|
| `rtk_fix` | `sensor.rtk` | RTK定位数据输入 |

### 输出端口

无（汇节点）

## 参数说明

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `web_port` | integer | 8082 | Web界面端口 |
| `auto_record_interval` | float | 1.0 | 自动记录间隔（秒） |
| `max_records` | integer | 10 | 保留的最大记录文件数量 |
| `record_format` | string | csv | 记录文件格式（csv/json） |

## 数据格式

### 输入数据 (sensor.rtk)

```json
{
    "timestamp": 1703024780.123,
    "lat": 39.9042,
    "lon": 116.4074,
    "alt": 50.5,
    "heading": 1.57,
    "rtk_status": "FIXED",
    "rtk_quality": 4,
    "num_satellites": 18
}
```

### 输出记录文件格式

#### CSV 格式

```csv
index,timestamp,datetime,lat,lon,alt,heading,rtk_status,rtk_quality,num_satellites,source
1,1703024780.123,2023-12-20T10:00:00,39.90420000,116.40740000,50.5,90.0,FIXED,4,18,manual
```

#### JSON 格式

```json
{
    "metadata": {
        "name": "Record 0001",
        "created_at": 1703024780.123,
        "auto_record_interval": 1.0
    },
    "summary": {
        "count": 100,
        "start_time": "2023-12-20T10:00:00",
        "end_time": "2023-12-20T10:01:40",
        "duration_seconds": 100.5,
        "bounds": {
            "min_lat": 39.9041,
            "max_lat": 39.9050,
            "min_lon": 116.4073,
            "max_lon": 116.4080
        }
    },
    "points": [...]
}
```

## 使用方法

### 1. 作为 NodeFlow 节点运行

在配置文件中添加节点配置：

```yaml
nodes:
  - name: position_recorder
    package: position_recorder
    params:
      web_port: 8082

edges:
  - from: rtk_driver.rtk_fix
    to: position_recorder.rtk_fix
```

### 2. 独立模式运行（用于测试）

```bash
cd node-hub/position_recorder
python3 web_server.py --port 8082
```

### 3. 使用 Web 界面

1. 启动节点后，在浏览器中打开 `http://localhost:8082`
2. 等待 RTK 数据连接（状态显示"已连接"）
3. 点击"开始记录"按钮
4. 手动点击"添加当前点"记录位置，或启用"自动记录"
5. 点击"停止记录"保存文件
6. 在"已保存的记录"列表中下载或删除文件

## Web 界面功能

- **当前位置面板**: 显示当前 RTK 定位数据
- **记录控制**: 开始/停止记录、手动添加点、清空点
- **自动记录开关**: 启用/禁用自动记录模式
- **记录统计**: 显示已记录点数和记录时长
- **记录列表**: 查看、下载、删除已保存的记录

## 依赖项

```
flask>=2.0.0
flask-socketio>=5.0.0
```

## 注意事项

1. 确保输入的 RTK 数据质量良好（固定解优先）
2. 记录文件保存在 `data/records/` 目录
3. 旧记录会自动删除，保留最近 N 次记录
4. Web 界面需要 JavaScript 支持
