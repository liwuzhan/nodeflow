# 地块规划节点 (Parcel Planner)

地块规划节点，支持 GPS 坐标转 ENU 坐标，提供 Web 界面进行地块绘制。

## 功能特性

- **GPS 坐标转换**：将 WGS84 GPS 坐标转换为局部 ENU 坐标系
- **Web 界面**：高德地图 API 界面，可视化绘制地块边界
- **双模式运行**：
  - **独立工具模式**：框架外独立运行，用于地块配置
  - **节点模式**：作为 NodeFlow 节点运行，输出 `task_enu` 数据

## 目录结构

```
parcel_planner/
├── node.yaml              # 节点配置
├── run.py                 # L3层 - 节点主逻辑
├── atom.py                # L4层 - 坐标转换算法
├── web_server.py          # Web服务器（Flask + SocketIO）
├── test_tool.py           # 独立工具模式入口
├── requirements.txt       # 依赖
├── data/                  # 数据存储目录
│   └── parcels/           # 保存的地块配置文件
└── README.md              # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
cd node-hub/parcel_planner
pip install -r requirements.txt
```

### 2. 设置高德地图 API Key

**方式 1：配置文件（推荐）**

编辑 `config.json`：
```json
{
  "amap_api_key": "your_api_key_here",
  "web_port": 8081,
  "web_host": "0.0.0.0"
}
```

**方式 2：环境变量**
```bash
export AMAP_API_KEY=your_api_key_here
```

**方式 3：命令行参数**
```bash
python3 test_tool.py --api-key your_api_key_here
```

配置优先级：命令行参数 > 环境变量 > 配置文件 > 默认值

免费申请地址：https://console.amap.com/dev/key/app

### 3. 运行独立工具

```bash
python3 test_tool.py
```

浏览器访问 http://localhost:8081

### 4. 绘制地块

1. **设置 GPS 参考点**：
   - 方式1：点击"📍 在地图选点"，在地图上选择
   - 方式2：手动输入经纬度，点击"从输入设置"

2. **绘制地块边界**：
   - 点击"✏️ 绘制边界"
   - 在地图上点击添加边界点
   - 点击"✓ 完成绘制"结束
   - 支持"↩️ 撤销点"和"清除绘制"

3. **配置车辆参数**：
   - 作业幅宽（米）
   - 重叠率（0-0.5）
   - 路径内缩（米）

4. **保存地块**：
   - 输入地块名称和描述
   - 点击"保存地块"

## 节点模式

作为 NodeFlow 节点运行：

```yaml
nodes:
  - id: parcel_planner
    package: parcel_planner
    params:
      parcel_name: "default"
```

### 输出端口

| 端口名 | 类型 | 描述 |
|--------|------|------|
| task_enu | planning.task_enu | 规划任务（ENU坐标+参考点） |

### 输出格式

```python
{
    'id': 'parcel_<name>',
    'parcel': {
        'outer': [(x, y), ...],  # ENU 坐标边界点
        'holes': [],
        'points': []
    },
    'vehicle': {
        'implement_width_m': 2.0,
        'overlap_ratio': 0.1,
        'path_inset_m': 0.5
    },
    'ref_lon': 121.5,
    'ref_lat': 31.2,
    'timestamp': 1234567890.0
}
```

## API 接口

### HTTP 接口

- `GET /` - Web 界面
- `GET /api/parcels` - 获取地块列表
- `POST /api/parcels` - 保存地块
- `GET /api/parcels/<name>` - 获取指定地块
- `DELETE /api/parcels/<name>` - 删除地块
- `POST /api/convert` - 坐标转换

### WebSocket 事件

| 事件 | 方向 | 描述 |
|------|------|------|
| set_ref_point | client→server | 设置 GPS 参考点 |
| update_boundary | client→server | 更新边界 |
| clear_boundary | client→server | 清除边界 |
| save_parcel | client→server | 保存地块 |
| load_parcel | client→server | 加载地块 |
| get_parcels | client→server | 获取地块列表 |
| parcel_update | server→client | 推送更新 |
| parcel_loaded | server→client | 地块加载完成 |
| parcel_saved | server→client | 地块保存完成 |
| parcels_list | server→client | 地块列表 |
| convert_to_enu | client→server | GPS转ENU（实时） |
| enu_result | server→client | ENU转换结果 |

## 坐标系说明

### GPS 坐标系 (WGS84)
- 经度 (longitude)：-180° ~ 180°
- 纬度 (latitude)：-90° ~ 90°
- GPS 设备直接输出的坐标

### ENU 坐标系 (East-North-Up)
- 原点：用户指定的 GPS 参考点
- X轴：东方向（米）
- Y轴：北方向（米）
- 用于局部路径规划

### 转换公式

```python
# GPS -> ENU
x = (lon - ref_lon) * meters_per_degree_lon(ref_lat)
y = (lat - ref_lat) * METERS_PER_DEGREE_LAT

# ENU -> GPS
lon = ref_lon + (x / meters_per_degree_lon(ref_lat))
lat = ref_lat + (y / METERS_PER_DEGREE_LAT)
```

## 数据文件格式

地块配置保存为 JSON 格式：

```json
{
  "name": "default",
  "description": "默认地块配置",
  "ref_point": {
    "lon": 121.5,
    "lat": 31.2,
    "description": "GPS参考点（地块原点）"
  },
  "boundary_gps": [
    [121.5001, 31.2001],
    [121.5002, 31.2001],
    [121.5002, 31.2002],
    [121.5001, 31.2002]
  ],
  "boundary_enu": [
    [11.1, 11.1],
    [22.2, 11.1],
    [22.2, 22.2],
    [11.1, 22.2]
  ],
  "vehicle": {
    "implement_width_m": 2.0,
    "overlap_ratio": 0.1,
    "path_inset_m": 0.5
  },
  "stats": {
    "area": 123.45,
    "perimeter": 44.4,
    "points": 4
  },
  "created_at": "2025-01-27T10:00:00",
  "updated_at": "2025-01-27T10:00:00"
}
```

## 参数配置

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| parcel_name | string | "default" | 地块配置名称 |
| web_port | integer | 8081 | Web界面端口（独立模式） |
| amap_api_key | string | - | 高德地图API Key |

## 依赖

- Flask >= 3.0.0
- Flask-SocketIO >= 5.0.0
- Pydantic >= 2.0.0
- Requests >= 2.0.0

## 工作流程

### 首次配置地块

1. 运行 `python3 test_tool.py`
2. 浏览器打开 http://localhost:8081
3. 设置 GPS 参考点
4. 绘制地块边界
5. 配置车辆参数
6. 保存地块配置

### 运行数据流

1. 配置 YAML 指定地块名称
2. 运行 NodeFlow
3. 节点自动加载地块配置
4. 输出 `task_enu` 到 `coord_transform`
