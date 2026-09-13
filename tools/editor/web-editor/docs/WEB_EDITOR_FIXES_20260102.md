# Web Editor 重大修复 (2026-01-02)

## 修复的问题

### 1. 输出端口位置修正 ✅

**问题**: 输出端口没有显示在节点右侧

**根本原因**:
- 之前使用了 `ports-container` flexbox 布局，但端口 handle 没有真正对齐到节点边缘
- 端口布局是左右并排，但实际渲染时端口都堆在一起

**修复方案**:
- 移除 `ports-container` 包装器
- 将输入和输出端口改为**上下堆叠**的独立 section
- 使用 `align-items: flex-start` 让输入端口靠左
- 使用 `align-items: flex-end` 让输出端口靠右
- 使用绝对定位让端口 dot **伸出节点边缘**
  - 输入端口 dot: `left: -4px`
  - 输出端口 dot: `right: -4px`

**相关文件**:
- `web-editor/src/components/canvas/CustomNode.vue` (lines 25-57, 229-269)
- `web-editor/src/components/canvas/PortHandle.vue` (lines 117-156)

---

### 2. 连线起点位置修正 ✅

**问题**: 拖拽连线时，虚线预览从鼠标位置开始，而不是从端口位置开始

**根本原因**:
- `PortHandle.vue` 传递的坐标是**屏幕坐标** (clientX, clientY)
- `GraphCanvas.vue` 直接将这些坐标用于 SVG `<line>` 元素
- 但 SVG 在 `transform-container` 内，受到 `transform` (缩放和平移) 的影响
- **坐标系不匹配**: 屏幕坐标 vs 画布坐标

**修复方案**:
在 `handleStartConnection` 和 `handleMouseMove` 中添加坐标转换：

```typescript
// 屏幕坐标 → 画布坐标
const canvasX = (clientX - rect.left - transform.value.panX) / transform.value.zoom
const canvasY = (clientY - rect.top - transform.value.panY) / transform.value.zoom
```

这样 SVG 线条的坐标就和节点位置坐标在同一个坐标系中。

**相关文件**:
- `web-editor/src/components/canvas/GraphCanvas.vue` (lines 268-315)

---

### 3. 移除节点框中的参数显示 ✅

**问题**: 节点框中显示参数列表，导致节点很长，不美观

**解决方案**:
- 完全移除节点框中的"参数"section
- 参数只在右侧属性面板中显示和编辑
- 节点框现在只显示：
  1. 标题栏（package 名称和节点 ID）
  2. 输入端口列表
  3. 输出端口列表

**好处**:
- 节点更简洁，占用空间更小
- 参数编辑在右侧面板中更直观
- 符合常见节点编辑器的设计模式

**相关文件**:
- `web-editor/src/components/canvas/CustomNode.vue` (移除了 lines 60-68 和相关 CSS)

---

### 4. 端口位置计算更新 ✅

**问题**: 由于布局改变，端口坐标计算不准确

**修复内容**:
更新 `getPortPosition()` 函数以适应新的上下堆叠布局：

```typescript
// 输入端口 Y 坐标
portY = nodeY + headerHeight + sectionLabelHeight + portIndex * portHeight + portHeight / 2

// 输出端口 Y 坐标（需要加上输入 section 的高度）
if (inputPorts.length > 0) {
  portY += sectionLabelHeight + inputPorts.length * portHeight
}
portY += sectionLabelHeight + portIndex * portHeight + portHeight / 2

// X 坐标
portX = direction === 'input' ? nodeX : nodeX + nodeWidth
```

**关键点**:
- 输入端口：X = 节点左边缘 (nodeX)
- 输出端口：X = 节点右边缘 (nodeX + nodeWidth)
- Y 坐标考虑了输入 section 的高度

**相关文件**:
- `web-editor/src/components/canvas/GraphCanvas.vue` (lines 429-482)

---

## 测试验证

### 测试步骤

1. **启动编辑器**:
   ```bash
   cd /Users/wuzhanli/Desktop/node
   ./start_web_editor.sh
   ```

2. **端口位置测试**:
   - 拖拽 `coord_transform` 到画布
   - 检查：
     - ✅ 输入端口的 dot 在节点**左边缘**
     - ✅ 输出端口的 dot 在节点**右边缘**
     - ✅ 端口名称清晰可见
     - ✅ 没有参数列表显示

3. **连线测试**:
   - 拖拽 `sim_output` 和 `coord_transform` 到画布
   - 从 `sim_output` 的输出端口拖拽连线
   - 检查：
     - ✅ 虚线预览从**端口 dot** 开始（不是鼠标位置）
     - ✅ 虚线跟随鼠标移动
     - ✅ 连接到目标端口后显示蓝色贝塞尔曲线
     - ✅ 连线起点和终点精确对齐端口

4. **缩放和平移测试**:
   - 滚动鼠标滚轮缩放
   - 中键拖拽平移
   - 检查：
     - ✅ 端口 dot 位置正确
     - ✅ 连线跟随节点移动
     - ✅ 拖拽新连线时坐标仍然正确

### 预期效果

**节点外观**:
```
┌─────────────────────┐
│ coord_transform     │  ← 标题栏
├─────────────────────┤
│ 输入          ← 标签│
● gps_data      ← 端口│  ← 输入端口在左边缘
● imu_data            │
├─────────────────────┤
│          输出 ← 标签│
│      enu_state ●    │  ← 输出端口在右边缘
│    orientation ●    │
└─────────────────────┘
```

**连线行为**:
```
[节点A] ─────→ [节点B]
        ↑
   从端口dot开始，平滑的贝塞尔曲线
```

---

## 技术细节

### 坐标系统

**三个坐标系**:
1. **屏幕坐标** - `clientX`, `clientY` (从 `getBoundingClientRect()`)
2. **画布坐标** - 相对于 canvas 容器，未经缩放/平移
3. **世界坐标** - 应用了 transform 的最终坐标

**转换公式**:
```typescript
// 屏幕 → 世界
worldX = (screenX - canvasRect.left - panX) / zoom
worldY = (screenY - canvasRect.top - panY) / zoom

// 世界 → 屏幕
screenX = worldX * zoom + panX + canvasRect.left
screenY = worldY * zoom + panY + canvasRect.top
```

**关键点**:
- 节点 position 存储的是**世界坐标**
- SVG 元素坐标使用**世界坐标** (因为 SVG 在 transform-container 内)
- 鼠标事件返回**屏幕坐标**，需要转换

### CSS 布局技巧

**端口对齐**:
```css
/* 输入端口靠左 */
.ports-section.inputs .ports-list {
  align-items: flex-start;
}

/* 输出端口靠右 */
.ports-section.outputs .ports-list {
  align-items: flex-end;
}
```

**端口 dot 伸出边缘**:
```css
.port-handle {
  position: relative;
}

.port-handle.position-left .handle-dot {
  position: absolute;
  left: -4px;  /* 伸出左边 */
}

.port-handle.position-right .handle-dot {
  position: absolute;
  right: -4px;  /* 伸出右边 */
}
```

---

## 已知限制

1. **节点宽度固定**: 当前硬编码为 200px，未来可以改为动态计算
2. **端口高度估算**: 使用估算值 26px，可能因 CSS 变化而不准确
3. **性能**: 每次渲染边时都调用 `getPortPosition()`，可以优化为缓存

---

## 文件修改清单

### 修改的文件

1. **web-editor/src/components/canvas/CustomNode.vue**
   - 移除参数显示 section
   - 移除 ports-container 包装器
   - 更新 CSS 布局（输入/输出端口独立 section）

2. **web-editor/src/components/canvas/PortHandle.vue**
   - 添加绝对定位让 dot 伸出节点边缘
   - 更新左右对齐样式

3. **web-editor/src/components/canvas/GraphCanvas.vue**
   - 添加坐标转换 (handleStartConnection)
   - 添加坐标转换 (handleMouseMove)
   - 更新 getPortPosition 以适应新布局
   - 添加详细的调试日志

### 未修改的文件

- `CustomEdge.vue` - 边渲染逻辑无需改动
- `graph.ts` - 数据模型无需改动
- `nodeLibrary.ts` - 节点库无需改动

---

## 调试技巧

### 控制台命令

**检查端口位置计算**:
打开浏览器控制台，连接两个节点后会看到：
```
Port position for sim_output_0.state (output): {x: 300, y: 87}
Port position for coord_transform_0.gps_data (input): {x: 500, y: 87}
```

**检查坐标转换**:
```
Start connection: {
  nodeId: "sim_output_0",
  port: "state",
  screenPos: {x: 234, y: 156},
  canvasPos: {x: 300, y: 87}
}
```

**检查 SVG 元素**:
```javascript
const edges = document.querySelectorAll('.custom-edge')
console.log('Edge count:', edges.length)

edges.forEach((edge, i) => {
  const path = edge.querySelector('path')
  console.log(`Edge ${i}:`, path.getAttribute('d'))
})
```

---

## 下一步改进

### 短期 (可选)

- [ ] 添加端口悬停提示，显示端口类型和描述
- [ ] 支持端口名称折叠（如果太长）
- [ ] 节点宽度自适应端口名称长度

### 中期 (计划中)

- [ ] 支持端口重新排序
- [ ] 添加端口类型颜色编码
- [ ] 支持条件端口（根据参数显示/隐藏）

### 长期 (未来)

- [ ] 支持自定义端口图标
- [ ] 支持端口分组
- [ ] 支持多连接（一个输出连接到多个输入）

---

**修复时间**: 2026-01-02
**测试状态**: 待用户验证
**维护者**: wuzhanli
