# 静态资源目录

此目录包含地块规划 Web 界面的静态资源文件（CSS 和 JavaScript）。

## 目录结构

```
static/
├── css/
│   └── style.css      # 界面样式（296 行）
└── js/
    └── app.js         # 前端逻辑（816 行）
```

## 文件说明

### style.css

包含所有 UI 组件的样式定义：

- **布局样式**
  - `.header` - 顶部导航栏
  - `.main-container` - 主容器（侧边栏 + 地图）
  - `.sidebar` - 左侧控制面板
  - `.map-container` - 右侧地图容器

- **表单组件**
  - `.form-group` - 表单输入组
  - `.form-row` - 水平表单布局
  - `.btn-*` - 按钮样式（primary, success, danger, secondary）

- **地块列表**
  - `.parcel-item` - 地块列表项
  - `.parcel-item.active` - 激活状态
  - `.parcel-actions` - 操作按钮容器

- **地图控件**
  - `.map-controls` - 右上角操作按钮组
  - `.coordinate-display` - 左下角坐标显示

- **状态提示**
  - `.alert-*` - 提示框（info, success, warning, error）
  - `.mode-badge` - 模式徽章（idle, draw, hole）

### app.js

包含所有前端交互逻辑：

#### 全局状态
```javascript
- map              // 高德地图实例
- socket           // Socket.IO 连接
- refPoint         // GPS 参考点
- boundaryMarkers  // 边界标记点
- holes            // 孔洞列表
- currentParcel    // 当前地块
```

#### 主要功能模块

**地图初始化**
- `initMap()` - 初始化高德地图
- `initSocket()` - 初始化 WebSocket 连接

**参考点管理**
- `setRefPoint(lon, lat)` - 设置 GPS 参考点
- `setRefPointFromInput()` - 从输入框设置
- `enableRefPointPick()` - 启用地图选点模式

**边界绘制**
- `enableDrawMode()` - 启用边界绘制模式
- `addBoundaryPoint(lon, lat)` - 添加边界点
- `updateBoundaryPolyline()` - 更新边界折线
- `undoPoint()` - 撤销最后一个点
- `clearBoundary()` - 清除所有边界

**孔洞管理**
- `enableHoleMode()` - 启用孔洞绘制模式
- `addHolePoint(lon, lat)` - 添加孔洞点
- `finishHole()` - 完成当前孔洞
- `clearHoles()` - 清除所有孔洞

**地块操作**
- `saveParcel()` - 保存地块
- `loadParcel(name)` - 加载地块
- `deleteParcel(name)` - 删除地块
- `refreshParcels()` - 刷新地块列表

**视图控制**
- `fitView()` - 自动调整视图以显示所有标记
- `updateCursorDisplay(lon, lat)` - 更新鼠标位置显示

#### WebSocket 事件

**接收事件**
- `connect` - 连接成功
- `disconnect` - 连接断开
- `parcel_update` - 地块数据更新
- `parcel_loaded` - 地块加载完成
- `parcel_saved` - 地块保存成功
- `parcel_deleted` - 地块删除成功
- `parcels_list` - 地块列表更新
- `enu_result` - ENU 坐标转换结果

**发送事件**
- `set_ref_point` - 设置参考点
- `update_boundary` - 更新边界
- `clear_boundary` - 清除边界
- `save_parcel` - 保存地块
- `load_parcel` - 加载地块
- `delete_parcel` - 删除地块
- `get_parcels` - 获取地块列表
- `convert_to_enu` - GPS 转 ENU

## 开发说明

### 修改样式

编辑 `css/style.css` 文件，修改后刷新浏览器即可看到效果（浏览器会重新加载 CSS）。

### 修改逻辑

编辑 `js/app.js` 文件，修改后需要：
1. 保存文件
2. 硬刷新浏览器（Ctrl+Shift+R 或 Cmd+Shift+R）

### 调试技巧

**查看控制台日志**
```javascript
// app.js 中添加调试日志
console.log('当前状态:', {refPoint, boundaryMarkers, holes});
```

**检查 WebSocket 通信**
```javascript
// 在浏览器控制台查看 WebSocket 消息
socket.onAny((event, ...args) => {
    console.log('Socket 事件:', event, args);
});
```

**检查地图对象**
```javascript
// 在浏览器控制台
console.log(map.getCenter());  // 地图中心
console.log(map.getZoom());    // 缩放级别
```

## 性能优化

### CSS
- 已使用 Flexbox 布局
- 使用 CSS 变量可进一步优化（未来改进）
- 考虑使用 CSS 预处理器（如 SCSS）

### JavaScript
- 使用事件委托减少事件监听器
- 使用防抖/节流优化频繁触发的事件
- 考虑使用 Web Workers 处理大量计算

## 浏览器兼容性

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

不支持 IE 浏览器。

## 第三方库

- **Socket.IO** 4.5.4 - WebSocket 通信
- **高德地图** 2.0 - 地图显示和交互

## 许可证

与 NodeFlow 项目保持一致。
