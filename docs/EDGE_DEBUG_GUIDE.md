# 连线不显示问题 - 调试指南

## 最新修复 (2026-01-02)

### 已修复的问题

#### 1. 输出端口位置修正 ✅
**问题**: 输出端口显示在左侧，应该在右侧

**修复内容**:
- 更新 `CustomNode.vue` 布局：将输入和输出端口改为左右并排显示
- 添加 `.ports-container` 使用 flexbox 布局
- 输入端口在左半部分，输出端口在右半部分
- PortHandle 组件已经支持 `position-right` 样式（反向布局）

**相关文件**:
- `web-editor/src/components/canvas/CustomNode.vue` (lines 25-60, 243-283)

#### 2. 连线坐标计算增强 ✅
**修复内容**:
- 更新 `getPortPosition()` 函数，添加调试日志
- 调整端口高度计算（26px，包含 gap）
- 添加错误检查和警告信息

**相关文件**:
- `web-editor/src/components/canvas/GraphCanvas.vue` (lines 416-454)

---

## 调试步骤

### 1. 检查端口是否正确显示

启动编辑器后：

1. 拖拽两个节点到画布（例如 `sim_output` 和 `rtk_filter`）
2. 检查每个节点：
   - **输入端口**应该在节点**左侧**
   - **输出端口**应该在节点**右侧**
3. 如果端口位置不对，检查浏览器控制台是否有 CSS 错误

### 2. 检查连线是否创建

在浏览器控制台中运行：

```javascript
// 检查图数据
const graphStore = window.__VUE_DEVTOOLS_GLOBAL_HOOK__.apps[0]?._instance?.proxy?.$pinia?.state?.value?.graph
console.log('Nodes:', graphStore?.nodes)
console.log('Edges:', graphStore?.edges)
```

或者：

```javascript
// 检查 SVG 中的边元素
const edges = document.querySelectorAll('.custom-edge')
console.log('Edge count in DOM:', edges.length)

edges.forEach((edge, i) => {
  const path = edge.querySelector('path')
  console.log(`Edge ${i} path:`, path.getAttribute('d'))
})
```

### 3. 检查端口坐标计算

连接两个节点后，查看控制台输出：

```
Port position for sim_output_1.state (output): {x: 300, y: 123}
Port position for rtk_filter_1.sim_state (input): {x: 500, y: 123}
```

- **正常情况**: x, y 值应该是合理的正数
- **异常情况**: 如果看到 (0, 0) 或者 NaN，说明坐标计算有问题

### 4. 检查 SVG 可见性

在浏览器开发者工具中：

1. 打开 Elements 标签
2. 找到 `<svg class="edges-layer">`
3. 检查：
   - SVG 尺寸应该是 10000x10000px
   - 里面应该有 `<g class="custom-edge">` 元素
   - 每个 edge 应该包含 `<path>` 元素
   - path 的 `d` 属性应该有合理的坐标值

### 5. 临时添加 SVG 背景色

如果怀疑 SVG 位置不对，可以在浏览器控制台中运行：

```javascript
document.querySelector('.edges-layer').style.background = 'rgba(255, 0, 0, 0.1)'
```

这会给 SVG 添加半透明红色背景，方便查看 SVG 的实际区域。

---

## 已知问题和解决方案

### 问题 1: SVG 尺寸太小，连线被裁剪

**症状**: 节点很远时连线不显示

**解决方案**: 已将 SVG 尺寸设置为 10000x10000px，应该足够大

**验证**:
```javascript
const svg = document.querySelector('.edges-layer')
console.log('SVG width:', svg.getAttribute('width'))
console.log('SVG height:', svg.getAttribute('height'))
```

### 问题 2: 坐标系不一致

**症状**: 连线位置不对，或者完全看不见

**原因**: SVG 和节点容器的坐标系不同步

**解决方案**:
- SVG 和节点容器都在同一个 `transform-container` 内
- 都应用相同的 transform（缩放和平移）
- 端口位置计算直接使用世界坐标（不需要考虑 transform）

### 问题 3: 端口位置计算不准确

**症状**: 连线起点或终点偏离端口

**可能原因**:
1. 节点布局变化后，端口高度/位置计算需要更新
2. CSS 变化影响了实际渲染尺寸

**调试**:
- 检查 `getPortPosition()` 的日志输出
- 手动测量端口在屏幕上的实际位置
- 对比计算值和实际值

---

## 测试场景

### 基础连接测试

1. 拖拽 `sim_output` 到画布 (100, 100)
2. 拖拽 `rtk_filter` 到画布 (400, 100)
3. 从 `sim_output` 的输出端口 `state` 拖拽到 `rtk_filter` 的输入端口 `sim_state`
4. **预期结果**:
   - 应该看到一条蓝色贝塞尔曲线
   - 从 sim_output 右侧连接到 rtk_filter 左侧
   - 鼠标悬停时线条变粗
   - 点击线条可以选中（虚线动画）

### 缩放和平移测试

1. 完成基础连接后
2. 滚动鼠标滚轮缩放画布
3. 中键拖拽平移画布
4. **预期结果**:
   - 连线应该随节点一起缩放和平移
   - 连接点始终在端口上

### 多节点连接测试

1. 添加 3-4 个节点
2. 创建多条连接
3. **预期结果**:
   - 所有连线都应该正确显示
   - 不同类型的端口显示不同颜色
   - 连线不应该重叠或交叉混乱

---

## 如果问题仍然存在

### 备选方案 1: 使用 DOM 坐标

如果 SVG 坐标计算始终有问题，可以改用 DOM API 实时获取端口位置：

```typescript
function getPortPositionFromDOM(nodeId: string, portName: string, direction: 'input' | 'output') {
  const nodeElement = document.querySelector(`[data-node-id="${nodeId}"]`)
  const portElement = nodeElement?.querySelector(`[data-port-name="${portName}"][data-position="${direction === 'input' ? 'left' : 'right'}"]`)

  if (portElement) {
    const rect = portElement.getBoundingClientRect()
    const canvasRect = canvasRef.value?.getBoundingClientRect()

    // 转换为画布坐标
    const x = (rect.left + rect.width / 2 - canvasRect.left - transform.value.panX) / transform.value.zoom
    const y = (rect.top + rect.height / 2 - canvasRect.top - transform.value.panY) / transform.value.zoom

    return { x, y }
  }

  return { x: 0, y: 0 }
}
```

**优点**: 完全准确，跟随实际 DOM 位置
**缺点**: 性能较差，需要频繁查询 DOM

### 备选方案 2: 使用第三方库

如果自己实现的节点编辑器问题太多，可以考虑：

- **Vue Flow**: https://vueflow.dev/
- **React Flow** (可以在 Vue 中使用): https://reactflow.dev/

这些库已经解决了所有坐标计算、缩放、连线等问题。

---

## 成功标志

如果看到以下情况，说明修复成功：

✅ 输入端口在节点左侧，输出端口在节点右侧
✅ 拖拽连接时显示虚线预览
✅ 释放鼠标后创建正确的连接线
✅ 连线起点和终点精确对齐端口
✅ 缩放和平移时连线跟随节点移动
✅ 鼠标悬停和点击连线有正确的交互反馈
✅ 浏览器控制台输出正确的端口坐标信息

---

## 相关文件清单

- `web-editor/src/components/canvas/GraphCanvas.vue` - 画布容器和坐标计算
- `web-editor/src/components/canvas/CustomNode.vue` - 节点组件和端口布局
- `web-editor/src/components/canvas/CustomEdge.vue` - 连线渲染
- `web-editor/src/components/canvas/PortHandle.vue` - 端口手柄组件
- `web-editor/src/stores/graph.ts` - 图数据管理
- `web-editor/src/services/typeChecker.ts` - 端口类型检查

---

**更新时间**: 2026-01-02
**维护者**: wuzhanli
