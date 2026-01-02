<template>
  <div
    ref="canvasRef"
    class="graph-canvas"
    @dragover.prevent="handleDragOver"
    @drop="handleDrop"
    @click="handleCanvasClick"
    @mousemove="handleMouseMove"
    @mouseup="handleMouseUp"
    @mousedown="handleMouseDown"
    @wheel.prevent="handleWheel"
  >
    <!-- 画布背景网格 -->
    <div class="canvas-grid" :style="gridStyle"></div>

    <!-- 变换容器 -->
    <div class="transform-container" :style="transformStyle">
      <!-- SVG层 - 渲染所有连接线 -->
      <svg class="edges-layer" width="10000" height="10000">
        <!-- 已存在的边 -->
        <CustomEdge
          v-for="[edgeId, edge] in graphStore.edges"
          :key="edgeId"
          :edge-id="edgeId"
          :from-node-id="edge.from_node"
          :from-port="edge.from_port"
          :from-port-type="getPortType(edge.from_node, edge.from_port, 'output')"
          :from-x="getPortPosition(edge.from_node, edge.from_port, 'output').x"
          :from-y="getPortPosition(edge.from_node, edge.from_port, 'output').y"
          :to-node-id="edge.to_node"
          :to-port="edge.to_port"
          :to-port-type="getPortType(edge.to_node, edge.to_port, 'input')"
          :to-x="getPortPosition(edge.to_node, edge.to_port, 'input').x"
          :to-y="getPortPosition(edge.to_node, edge.to_port, 'input').y"
          :is-selected="graphStore.selectedEdgeId === edgeId"
          @select="() => graphStore.selectEdge(edgeId)"
          @delete="() => graphStore.deleteEdge(edgeId)"
        />

        <!-- 连接预览线 -->
        <line
          v-if="connectionState.connecting"
          :x1="connectionState.startX"
          :y1="connectionState.startY"
          :x2="connectionState.currentX"
          :y2="connectionState.currentY"
          stroke="#409eff"
          stroke-width="2"
          stroke-dasharray="5,5"
          fill="none"
          class="connection-preview"
        />
      </svg>

      <!-- 节点容器 -->
      <div class="nodes-container">
        <CustomNode
          v-for="nodeId in graphStore.allNodeIds"
          :key="nodeId"
          :node-id="nodeId"
          :node="graphStore.getNode(nodeId)!"
          :is-selected="graphStore.selectedNodeId === nodeId"
          :port-connections="getNodePortConnections(nodeId)"
          @select="() => graphStore.selectNode(nodeId)"
          @update-position="(pos) => graphStore.updateNodePosition(nodeId, pos)"
          @delete="() => graphStore.deleteNode(nodeId)"
          @start-connect="handleStartConnection"
          @disconnect-port="(portName) => handleDisconnectPort(nodeId, portName)"
        />
      </div>
    </div>

    <!-- 提示文字 -->
    <div v-if="graphStore.nodeCount === 0" class="canvas-hint">
      <p>从左侧节点库拖拽节点到这里</p>
      <el-icon><DragEnd /></el-icon>
    </div>

    <!-- 拖拽预览 -->
    <div
      v-if="dragPreview.active"
      class="drag-preview"
      :style="{ left: dragPreview.x + 'px', top: dragPreview.y + 'px' }"
    >
      {{ dragPreview.packageName }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useGraphStore } from '@/stores/graph'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import { getInputPorts, getOutputPorts } from '@/models'
import CustomNode from './CustomNode.vue'
import CustomEdge from './CustomEdge.vue'
import type { ConnectionStartData } from './PortHandle.vue'
import { validateConnection } from '@/services/typeChecker'
import { ElMessage, ElMessageBox } from 'element-plus'

const graphStore = useGraphStore()
const nodeLibraryStore = useNodeLibraryStore()
const canvasRef = ref<HTMLElement | null>(null)

// 画布变换状态
const transform = ref({
  zoom: 1,
  panX: 0,
  panY: 0,
})

// 平移状态
const panState = ref({
  panning: false,
  startX: 0,
  startY: 0,
  initialPanX: 0,
  initialPanY: 0,
})

// 拖拽预览状态
const dragPreview = ref({
  active: false,
  x: 0,
  y: 0,
  packageName: '',
})

// 连接状态
const connectionState = ref({
  connecting: false,
  fromNodeId: '',
  fromPort: '',
  fromPortType: '',
  fromPosition: '' as 'left' | 'right',
  startX: 0,
  startY: 0,
  currentX: 0,
  currentY: 0,
})

// 变换样式
const transformStyle = computed(() => {
  return {
    transform: `translate(${transform.value.panX}px, ${transform.value.panY}px) scale(${transform.value.zoom})`,
    transformOrigin: '0 0',
  }
})

// 网格样式（随缩放调整）
const gridStyle = computed(() => {
  const gridSize = 20 * transform.value.zoom
  return {
    backgroundSize: `${gridSize}px ${gridSize}px`,
    backgroundPosition: `${transform.value.panX}px ${transform.value.panY}px`,
  }
})

function handleDragOver(e: DragEvent) {
  if (!e.dataTransfer) return

  e.dataTransfer.dropEffect = 'copy'

  // 显示拖拽预览
  dragPreview.value.active = true
  dragPreview.value.x = e.clientX - 100
  dragPreview.value.y = e.clientY - 60

  // 获取package名称
  const packageName = e.dataTransfer.getData('application/node-package')
  dragPreview.value.packageName = packageName
}

function handleDrop(e: DragEvent) {
  if (!e.dataTransfer) return

  e.preventDefault()
  dragPreview.value.active = false

  const packageName = e.dataTransfer.getData('application/node-package')

  if (!packageName) {
    console.warn('No package name in drag data')
    return
  }

  // 检查节点是否存在
  if (!nodeLibraryStore.hasPackage(packageName)) {
    console.error(`Package "${packageName}" not found`)
    return
  }

  // 获取canvas相对位置，并应用逆变换
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const clientX = e.clientX - rect.left
  const clientY = e.clientY - rect.top

  // 应用逆变换：从屏幕坐标转换为世界坐标
  const worldX = (clientX - transform.value.panX) / transform.value.zoom - 50
  const worldY = (clientY - transform.value.panY) / transform.value.zoom - 30

  // 添加节点
  try {
    const nodeId = graphStore.addNode(packageName, { x: worldX, y: worldY })
    console.log(`Added node to canvas: ${nodeId} at (${worldX}, ${worldY})`)
  } catch (error) {
    console.error('Failed to add node:', error)
  }
}

function handleCanvasClick(e: MouseEvent) {
  // 如果正在平移，不处理点击
  if (panState.value.panning) {
    return
  }

  // 如果正在连接，取消连接
  if (connectionState.value.connecting) {
    connectionState.value.connecting = false
    return
  }

  // 如果点击的是canvas自身（不是节点），取消选择
  if ((e.target as HTMLElement).classList.contains('graph-canvas') ||
      (e.target as HTMLElement).classList.contains('canvas-grid') ||
      (e.target as HTMLElement).classList.contains('transform-container')) {
    graphStore.selectNode(null)
    graphStore.selectEdge(null)
  }
}

// 鼠标滚轮缩放
function handleWheel(e: WheelEvent) {
  if (!canvasRef.value) return

  const rect = canvasRef.value.getBoundingClientRect()
  const mouseX = e.clientX - rect.left
  const mouseY = e.clientY - rect.top

  // 计算缩放前的世界坐标
  const worldX = (mouseX - transform.value.panX) / transform.value.zoom
  const worldY = (mouseY - transform.value.panY) / transform.value.zoom

  // 计算新的缩放级别
  const zoomDelta = -e.deltaY * 0.001
  const newZoom = Math.max(0.1, Math.min(3, transform.value.zoom + zoomDelta))

  // 更新缩放
  transform.value.zoom = newZoom

  // 调整平移，使鼠标位置保持不变
  transform.value.panX = mouseX - worldX * newZoom
  transform.value.panY = mouseY - worldY * newZoom
}

// 鼠标按下（开始平移）
function handleMouseDown(e: MouseEvent) {
  // 中键拖拽画布
  if (e.button === 1) {
    e.preventDefault()
    panState.value.panning = true
    panState.value.startX = e.clientX
    panState.value.startY = e.clientY
    panState.value.initialPanX = transform.value.panX
    panState.value.initialPanY = transform.value.panY
  }
}

// 开始连接
function handleStartConnection(data: ConnectionStartData) {
  if (!canvasRef.value) return

  // 将屏幕坐标转换为画布坐标
  const rect = canvasRef.value.getBoundingClientRect()
  const canvasX = (data.clientX - rect.left - transform.value.panX) / transform.value.zoom
  const canvasY = (data.clientY - rect.top - transform.value.panY) / transform.value.zoom

  connectionState.value.connecting = true
  connectionState.value.fromNodeId = data.nodeId
  connectionState.value.fromPort = data.portName
  connectionState.value.fromPortType = data.portType
  connectionState.value.fromPosition = data.position
  connectionState.value.startX = canvasX
  connectionState.value.startY = canvasY
  connectionState.value.currentX = canvasX
  connectionState.value.currentY = canvasY

  console.log('Start connection:', {
    nodeId: data.nodeId,
    port: data.portName,
    screenPos: { x: data.clientX, y: data.clientY },
    canvasPos: { x: canvasX, y: canvasY }
  })
}

// 鼠标移动（更新连接预览或平移画布）
function handleMouseMove(e: MouseEvent) {
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()

  // 优先处理平移
  if (panState.value.panning) {
    const deltaX = e.clientX - panState.value.startX
    const deltaY = e.clientY - panState.value.startY

    transform.value.panX = panState.value.initialPanX + deltaX
    transform.value.panY = panState.value.initialPanY + deltaY
    return
  }

  // 处理连接预览 - 转换为画布坐标
  if (connectionState.value.connecting) {
    const canvasX = (e.clientX - rect.left - transform.value.panX) / transform.value.zoom
    const canvasY = (e.clientY - rect.top - transform.value.panY) / transform.value.zoom
    connectionState.value.currentX = canvasX
    connectionState.value.currentY = canvasY
  }
}

// 鼠标释放（完成或取消连接，或结束平移）
function handleMouseUp(e: MouseEvent) {
  // 结束平移
  if (panState.value.panning) {
    panState.value.panning = false
    return
  }

  if (!connectionState.value.connecting) return

  // 检查是否在目标端口上释放
  const target = e.target as HTMLElement
  const portHandle = target.closest('.port-handle')

  if (portHandle) {
    // 获取目标端口信息（需要从DOM属性获取）
    const targetNodeElement = portHandle.closest('.custom-node')
    if (targetNodeElement) {
      const targetNodeId = targetNodeElement.getAttribute('data-node-id')
      const targetPortName = portHandle.getAttribute('data-port-name')
      const targetPortType = portHandle.getAttribute('data-port-type')
      const targetPosition = portHandle.getAttribute('data-position') as 'left' | 'right'

      if (targetNodeId && targetPortName && targetPortType) {
        attemptConnection(targetNodeId, targetPortName, targetPortType, targetPosition)
      }
    }
  }

  // 重置连接状态
  connectionState.value.connecting = false
}

// 尝试创建连接
function attemptConnection(
  toNodeId: string,
  toPort: string,
  toPortType: string,
  toPosition: 'left' | 'right'
) {
  const from = connectionState.value

  // 确定方向：output -> input
  let fromNodeId: string, fromPort: string, fromPortType: string
  let targetNodeId: string, targetPort: string, targetPortType: string

  if (from.fromPosition === 'right') {
    // 从输出端口开始，目标必须是输入端口
    if (toPosition !== 'left') {
      ElMessage.warning('只能从输出端口连接到输入端口')
      return
    }
    fromNodeId = from.fromNodeId
    fromPort = from.fromPort
    fromPortType = from.fromPortType
    targetNodeId = toNodeId
    targetPort = toPort
    targetPortType = toPortType
  } else {
    // 从输入端口开始，目标必须是输出端口
    if (toPosition !== 'right') {
      ElMessage.warning('只能从输出端口连接到输入端口')
      return
    }
    fromNodeId = toNodeId
    fromPort = toPort
    fromPortType = toPortType
    targetNodeId = from.fromNodeId
    targetPort = from.fromPort
    targetPortType = from.fromPortType
  }

  // 验证连接
  const validation = validateConnection(
    fromNodeId,
    fromPort,
    fromPortType,
    targetNodeId,
    targetPort,
    targetPortType
  )

  if (!validation.valid) {
    ElMessage.error(validation.errors.join('; '))
    return
  }

  // 创建边
  try {
    const edgeId = graphStore.addEdge(fromNodeId, fromPort, targetNodeId, targetPort, fromPortType)
    console.log(`Created edge: ${edgeId}`)
    ElMessage.success('连接创建成功')
  } catch (error) {
    console.error('Failed to create edge:', error)
    ElMessage.error('连接创建失败')
  }
}

// 获取端口类型
function getPortType(nodeId: string, portName: string, direction: 'input' | 'output'): string {
  const node = graphStore.getNode(nodeId)
  if (!node) return 'any'

  const manifest = nodeLibraryStore.getManifest(node.package)
  if (!manifest) return 'any'

  const ports = direction === 'input' ? getInputPorts(manifest) : getOutputPorts(manifest)
  const port = ports.find(p => p.name === portName)
  return port?.type || 'any'
}

// 获取端口在画布上的位置
function getPortPosition(nodeId: string, portName: string, direction: 'input' | 'output'): { x: number; y: number } {
  const node = graphStore.getNode(nodeId)
  if (!node) {
    console.warn(`getPortPosition: Node ${nodeId} not found`)
    return { x: 0, y: 0 }
  }

  const manifest = nodeLibraryStore.getManifest(node.package)
  if (!manifest) {
    console.warn(`getPortPosition: Manifest for ${node.package} not found`)
    return { x: 0, y: 0 }
  }

  const inputPorts = getInputPorts(manifest)
  const outputPorts = getOutputPorts(manifest)

  const ports = direction === 'input' ? inputPorts : outputPorts
  const portIndex = ports.findIndex(p => p.name === portName)

  if (portIndex === -1) {
    console.warn(`getPortPosition: Port ${portName} not found in ${direction} ports`)
    return { x: 0, y: 0 }
  }

  // 计算位置
  const nodeX = node.position.x
  const nodeY = node.position.y
  const nodeWidth = 200 // CustomNode最小宽度
  const headerHeight = 40
  const sectionLabelHeight = 24
  const portHeight = 20 // 更新：match PortHandle min-height

  // Y 坐标计算
  let portY = nodeY + headerHeight

  if (direction === 'input') {
    // 输入端口：从header下方开始
    portY += sectionLabelHeight + portIndex * portHeight + portHeight / 2
  } else {
    // 输出端口：需要加上输入section的高度（如果存在）
    if (inputPorts.length > 0) {
      portY += sectionLabelHeight + inputPorts.length * portHeight + 8 // 加上 border
    }
    portY += sectionLabelHeight + portIndex * portHeight + portHeight / 2
  }

  // X 坐标：输入在左侧边缘，输出在右侧边缘
  const portX = direction === 'input' ? nodeX : nodeX + nodeWidth

  console.log(`📍 Port ${nodeId}.${portName} (${direction}[${portIndex}]):`,
    `position=(${portX.toFixed(1)}, ${portY.toFixed(1)})`,
    `node=(${nodeX}, ${nodeY})`)

  return { x: portX, y: portY }
}

// 获取节点输入端口的连接状态
function getNodePortConnections(nodeId: string): Record<string, boolean> {
  const connections: Record<string, boolean> = {}

  // 遍历所有边，找出连接到此节点输入端口的边
  for (const [_, edge] of graphStore.edges) {
    if (edge.to_node === nodeId) {
      connections[edge.to_port] = true
    }
  }

  return connections
}

// 断开输入端口的连线
function handleDisconnectPort(nodeId: string, portName: string) {
  // 找到连接到此端口的边
  for (const [edgeId, edge] of graphStore.edges) {
    if (edge.to_node === nodeId && edge.to_port === portName) {
      graphStore.deleteEdge(edgeId)
      ElMessage.success('连线已断开')
      return
    }
  }
}

// 处理键盘事件
function handleKeyDown(e: KeyboardEvent) {
  // 如果正在输入（input/textarea），不处理
  if ((e.target as HTMLElement).tagName === 'INPUT' ||
      (e.target as HTMLElement).tagName === 'TEXTAREA') {
    return
  }

  // Delete 或 Backspace 删除选中的节点/连线
  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    deleteSelected()
  }
}

// 删除选中的节点或连线
function deleteSelected() {
  if (graphStore.selectedNodeId) {
    const nodeId = graphStore.selectedNodeId
    const node = graphStore.getNode(nodeId)

    ElMessageBox.confirm(
      `确定要删除节点 "${node?.package}" (${nodeId}) 吗？相关的连线也会被删除。`,
      '删除节点',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    ).then(() => {
      graphStore.deleteNode(nodeId)
      ElMessage.success('节点已删除')
    }).catch(() => {
      // 用户取消
    })
  } else if (graphStore.selectedEdgeId) {
    const edgeId = graphStore.selectedEdgeId
    graphStore.deleteEdge(edgeId)
    ElMessage.success('连线已删除')
  }
}

// 生命周期
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #fafafa;
  overflow: hidden;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }
}

.canvas-grid {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-image:
    linear-gradient(#e8e8e8 1px, transparent 1px),
    linear-gradient(90deg, #e8e8e8 1px, transparent 1px);
  background-size: 20px 20px;
  pointer-events: none;
  opacity: 0.5;
  transition: background-position 0.05s ease-out;
}

.transform-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 10000px;
  height: 10000px;
  will-change: transform;
}

.edges-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 10000px;
  height: 10000px;
  pointer-events: none;
  z-index: 1;
  overflow: visible;
}

.edges-layer > * {
  pointer-events: auto;
}

.connection-preview {
  animation: dash 0.5s linear infinite;
}

@keyframes dash {
  to {
    stroke-dashoffset: -10;
  }
}

.nodes-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 10000px;
  height: 10000px;
  z-index: 2;
}

.canvas-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #999;
  pointer-events: none;
  user-select: none;
  z-index: 0;

  p {
    font-size: 16px;
    margin: 0 0 12px 0;
  }

  i {
    font-size: 48px;
    opacity: 0.5;
  }
}

.drag-preview {
  position: fixed;
  padding: 8px 12px;
  background-color: #409eff;
  color: white;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  pointer-events: none;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  white-space: nowrap;
}
</style>
