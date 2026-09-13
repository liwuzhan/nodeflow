# ENU → GPS 转换工具集

将ENU局部平面坐标转换回WGS84 GPS经纬度坐标。

## 推荐：batch_convert.py（批量自动转换）

**自动扫描目录、自动提取参考点、批量转换。**

### 快速使用

```bash
cd /Users/liwuzhan/Desktop/nodeflow/other/enu-gps
python3 batch_convert.py
```

### 文件格式要求

第一行必须包含参考点：
```
# piont: 120.425095,30.654390
```

### 运行示例

```
$ python3 batch_convert.py

目标目录: /Users/liwuzhan/Desktop/nodeflow/other/enu-gps

找到 1 个文件待转换
============================================================

处理: path_20260126_235026_task_1769442617.txt
  参考点: (120.425095°E, 30.654390°N)
  ✓ 转换成功: 76 个数据点
  输出: path_20260126_235026_task_1769442617_gps.txt

============================================================
完成: 1/1 个文件转换成功
```

### 功能特点

- ✓ 自动扫描目录下所有txt文件
- ✓ 自动从第一行提取参考点（支持 `piont`/`point`/`ref` 格式）
- ✓ 自动跳过已转换的文件（_gps.txt后缀）
- ✓ 保留所有注释和元数据

---

## 备选：enu_to_gps.py（手动指定参考点）

需要手动指定参考点的场景使用。

### 坐标系定义

**输入 (ENU):**
- `x`: 东向距离（米）
- `y`: 北向距离（米）
- `theta`: 航向角（弧度，东=0，逆时针CCW为正）
- 参考点: `ref_lon`, `ref_lat`

**输出 (WGS84):**
- `longitude`: 经度（度）
- `latitude`: 纬度（度）
- `heading`: 航向角（度，北=0，顺时针CW为正）

### 使用方法

#### 1. 文件批量转换（推荐）

```bash
# 基本用法（输出到默认文件：输入文件名_gps.txt）
python3 other/enu_to_gps.py \
  --file node-hub/global_coverage/txt/path_xxx.txt \
  --ref-lon 116.397128 \
  --ref-lat 39.916527

# 指定输出文件
python3 other/enu_to_gps.py \
  --file path.txt \
  --output gps_path.txt \
  --ref-lon 116.397128 \
  --ref-lat 39.916527
```

**支持的文件格式:**
- 注释行以 `#` 开头（会被保留）
- 数据行格式: `x, y` 或 `x, y, theta`
- 输出格式: `longitude, latitude` 或 `longitude, latitude, heading`

#### 2. 单点转换

```bash
# 基本用法（只转换位置）
python3 other/enu_to_gps.py \
  --x 100 \
  --y 200 \
  --ref-lon 116.397128 \
  --ref-lat 39.916527

# 包含航向角转换
python3 other/enu_to_gps.py \
  --x 100 \
  --y 200 \
  --theta 1.57 \
  --ref-lon 116.397128 \
  --ref-lat 39.916527

# JSON格式输出
python3 other/enu_to_gps.py \
  --x 100 \
  --y 200 \
  --ref-lon 116.397128 \
  --ref-lat 39.916527 \
  --json
```

#### 3. 交互模式

```bash
python3 other/enu_to_gps.py --interactive
```

交互模式下会提示输入参考点和坐标，支持连续转换多个点。

### 示例

#### 示例1: 批量转换路径文件

输入文件 `path.txt` (ENU坐标):
```
# Task ID: task_1769414446
# Format: x(m), y(m)
#--------------------------------------------------
-67.587757, -98.734686
-67.318238, -98.313593
-67.048719, -97.892500
...
```

运行转换:
```bash
python3 other/enu_to_gps.py \
  --file path.txt \
  --ref-lon 116.397128 \
  --ref-lat 39.916527
```

输出文件 `path_gps.txt` (GPS坐标):
```
# Task ID: task_1769414446
# Format: longitude(deg), latitude(deg)
#--------------------------------------------------
116.39633639, 39.91564006
116.39633955, 39.91564384
116.39634270, 39.91564762
...
```

转换结果:
```
✓ 转换完成: 3995 个数据点
  保存至: path_gps.txt
```

#### 示例2: 北京天安门附近坐标转换

参考点: 116.397128°E, 39.916527°N

向东100米，向北200米:
```bash
$ python3 other/enu_to_gps.py --x 100 --y 200 --ref-lon 116.397128 --ref-lat 39.916527
经度: 116.39829923
纬度: 39.91832362
```

#### 示例3: 包含航向角

ENU坐标 (100, 200) 米，航向角 π/2 弧度（指向北）:
```bash
$ python3 other/enu_to_gps.py --x 100 --y 200 --theta 1.57 --ref-lon 116.397128 --ref-lat 39.916527
经度: 116.39829923
纬度: 39.91832362
航向: 0.05°
```

#### 示例4: JSON输出（便于程序调用）

```bash
$ python3 other/enu_to_gps.py --x 100 --y 200 --ref-lon 116.397128 --ref-lat 39.916527 --json
{
  "input": {
    "x": 100.0,
    "y": 200.0,
    "ref_lon": 116.397128,
    "ref_lat": 39.916527
  },
  "output": {
    "longitude": 116.39829923,
    "latitude": 39.91832362
  }
}
```

### 常见参考点

**北京:**
- 天安门: 116.397128°E, 39.916527°N
- 鸟巢: 116.388, 39.992

**上海:**
- 外滩: 121.490, 31.240

**深圳:**
- 市民中心: 114.056, 22.548

### 验证方法

可以结合 `coord_transform` 节点进行往返验证:

```bash
# GPS → ENU → GPS 应该得到原始坐标
1. 使用 coord_transform 节点: (116.398, 39.917) → (x, y)
2. 使用 enu_to_gps.py: (x, y) → (116.398, 39.917)
```

### 技术细节

- 使用简化的平面近似（适合小范围 <10km）
- 纬度每度: 111,320米（固定）
- 经度每度: `111,320 * cos(纬度)` 米
- 地球半径: 6,371,000米
