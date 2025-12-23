<template>
  <div
    ref="canvasRef"
    class="graph-canvas"
    @dragover.prevent="handleDragOver"
    @drop="handleDrop"
    @click="handleCanvasClick"
    @mousemove="handleMouseMove"
    @mouseup="handleMouseUp"
  >
    <!-- 画布背景网格 -->
    <div class="canvas-grid"></div>

    <!-- SVG层 - 渲染所有连接线 -->
    <svg class="edges-layer">
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
        @select="() => graphStore.selectNode(nodeId)"
        @update-position="(pos) => graphStore.updateNodePosition(nodeId, pos)"
        @delete="() => graphStore.deleteNode(nodeId)"
        @start-connect="handleStartConnection"
      />
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
import { ref } from 'vue'
import { useGraphStore } from '@/stores/graph'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import CustomNode from './CustomNode.vue'
import CustomEdge from './CustomEdge.vue'
import type { ConnectionStartData } from './PortHandle.vue'
import { validateConnection } from '@/services/typeChecker'
import { ElMessage } from 'element-plus'

const graphStore = useGraphStore()
const nodeLibraryStore = useNodeLibraryStore()
const canvasRef = ref<HTMLElement | null>(null)

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

  // 获取canvas相对位置
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left - 50 // 中心对齐
  const y = e.clientY - rect.top - 30

  // 添加节点
  try {
    const nodeId = graphStore.addNode(packageName, { x, y })
    console.log(`Added node to canvas: ${nodeId} at (${x}, ${y})`)
  } catch (error) {
    console.error('Failed to add node:', error)
  }
}

function handleCanvasClick(e: MouseEvent) {
  // 如果正在连接，取消连接
  if (connectionState.value.connecting) {
    connectionState.value.connecting = false
    return
  }

  // 如果点击的是canvas自身（不是节点），取消选择
  if ((e.target as HTMLElement).classList.contains('graph-canvas') ||
      (e.target as HTMLElement).classList.contains('canvas-grid')) {
    graphStore.selectNode(null)
    graphStore.selectEdge(null)
  }
}

// 开始连接
function handleStartConnection(data: ConnectionStartData) {
  connectionState.value.connecting = true
  connectionState.value.fromNodeId = data.nodeId
  connectionState.value.fromPort = data.portName
  connectionState.value.fromPortType = data.portType
  connectionState.value.fromPosition = data.position
  connectionState.value.startX = data.clientX
  connectionState.value.startY = data.clientY
  connectionState.value.currentX = data.clientX
  connectionState.value.currentY = data.clientY

  console.log('Start connection:', data)
}

// 鼠标移动（更新连接预览）
function handleMouseMove(e: MouseEvent) {
  if (!connectionState.value.connecting) return

  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  connectionState.value.currentX = e.clientX - rect.left
  connectionState.value.currentY = e.clientY - rect.top
}

// 鼠标释放（完成或取消连接）
function handleMouseUp(e: MouseEvent) {
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

  const ports = direction === 'input' ? manifest.inputs : manifest.outputs
  const port = ports?.find(p => p.name === portName)
  return port?.type || 'any'
}

// 获取端口在画布上的位置
function getPortPosition(nodeId: string, portName: string, direction: 'input' | 'output'): { x: number; y: number } {
  const node = graphStore.getNode(nodeId)
  if (!node) return { x: 0, y: 0 }

  const manifest = nodeLibraryStore.getManifest(node.package)
  if (!manifest) return { x: 0, y: 0 }

  const ports = direction === 'input' ? manifest.inputs : manifest.outputs
  const portIndex = ports?.findIndex(p => p.name === portName) ?? -1

  if (portIndex === -1) return { x: 0, y: 0 }

  // 估算位置（基于节点位置和端口索引）
  // 节点头部约40px，端口高度约24px，起始偏移约60px
  const nodeX = node.position.x
  const nodeY = node.position.y
  const nodeWidth = 200 // CustomNode最小宽度
  const headerHeight = 40
  const portsLabelHeight = 24
  const portHeight = 24

  const portY = nodeY + headerHeight + portsLabelHeight + portIndex * portHeight + portHeight / 2

  // 输入端口在左侧，输出端口在右侧
  const portX = direction === 'input' ? nodeX : nodeX + nodeWidth

  return { x: portX, y: portY }
}
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
}

.edges-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
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
  position: relative;
  width: 100%;
  height: 100%;
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
