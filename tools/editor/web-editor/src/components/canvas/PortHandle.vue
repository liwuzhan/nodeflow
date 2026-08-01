<template>
  <div
    class="port-handle"
    :data-port-name="portName"
    :data-port-type="portType"
    :data-position="position"
    :class="[
      positionClass,
      { connecting: isConnecting, active: isActive, invalid: showInvalid, connected: isConnected },
    ]"
    :title="portTitle"
    @mousedown.stop="handleMouseDown"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <div class="handle-dot" :style="{ backgroundColor: dotColor }" />
    <span class="handle-label">{{ portName }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  nodeId: string
  portName: string
  portType: string
  position: 'left' | 'right' // 'left' for input, 'right' for output
  index: number // 端口在列表中的序号
  isConnected?: boolean // 是否有连线连接到此端口
}

interface Emits {
  (e: 'startConnect', data: ConnectionStartData): void
  (e: 'endConnect'): void
  (e: 'checkCompatibility', data: CompatibilityCheckData): void
  (e: 'disconnect'): void // 断开连线
}

export interface ConnectionStartData {
  nodeId: string
  portName: string
  portType: string
  position: 'left' | 'right'
  clientX: number
  clientY: number
}

export interface CompatibilityCheckData {
  fromNodeId: string
  fromPortType: string
  toNodeId: string
  toPortType: string
}

const props = withDefaults(defineProps<Props>(), {
  isConnected: false,
})
const emit = defineEmits<Emits>()

const isActive = ref(false)
const showInvalid = ref(false)
const isConnecting = ref(false)

// 端口CSS类名
const positionClass = computed(() => `position-${props.position}`)

// 端口提示信息
const portTitle = computed(() => {
  if (props.position === 'left' && props.isConnected) {
    return `${props.portName} (${props.portType}) - 点击断开连线`
  }
  return `${props.portName} (${props.portType})`
})

// 点的颜色（根据类型和状态）
const dotColor = computed(() => {
  if (showInvalid.value) {
    return '#f56c6c' // 红色 - 不兼容
  }
  if (isActive.value || isConnecting.value) {
    return '#409eff' // 蓝色 - 活跃/连接中
  }
  // 已连接的输入端口显示橙色
  if (props.position === 'left' && props.isConnected) {
    return '#e6a23c' // 橙色 - 已连接
  }
  if (props.portType === 'any') {
    return '#909399' // 灰色 - any类型
  }
  return '#67c23a' // 绿色 - 正常
})

function handleMouseDown(e: MouseEvent) {
  // 如果是输入端口且已连接，点击断开连线
  if (props.position === 'left' && props.isConnected) {
    emit('disconnect')
    return
  }

  // 否则开始连线
  startConnection(e)
}

function startConnection(e: MouseEvent) {
  const rect = (e.target as HTMLElement).getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2

  emit('startConnect', {
    nodeId: props.nodeId,
    portName: props.portName,
    portType: props.portType,
    position: props.position,
    clientX: centerX,
    clientY: centerY,
  })
}

function onMouseEnter() {
  isActive.value = true
}

function onMouseLeave() {
  isActive.value = false
  showInvalid.value = false
}

// 暴露方法给父组件检查兼容性
function setCompatibility(compatible: boolean) {
  showInvalid.value = !compatible
}

function setConnecting(connecting: boolean) {
  isConnecting.value = connecting
}

defineExpose({
  setCompatibility,
  setConnecting,
})
</script>

<style scoped>
.port-handle {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  cursor: crosshair;
  transition: all 0.2s;
  user-select: none;
  position: relative;
  min-height: 20px;
}

.port-handle:hover .handle-label {
  color: #409eff;
  font-weight: 500;
}

/* 输入端口：dot 在最左边，伸出节点边缘，label 在右边 */
.port-handle.position-left {
  justify-content: flex-start;
  padding-left: 8px;
}

.port-handle.position-left .handle-dot {
  position: absolute;
  left: -4px; /* 伸出节点左边缘 */
  top: 50%;
  transform: translateY(-50%);
}

.port-handle.position-left .handle-label {
  margin-left: 8px; /* 与左边缘保持距离 */
}

/* 输出端口：dot 在最右边，伸出节点边缘，label 在左边 */
.port-handle.position-right {
  justify-content: flex-end;
  padding-right: 8px;
}

.port-handle.position-right .handle-dot {
  position: absolute;
  right: -4px; /* 伸出节点右边缘 */
  top: 50%;
  transform: translateY(-50%);
}

.port-handle.position-right .handle-label {
  margin-right: 8px; /* 与右边缘保持距离 */
  text-align: right;
}

.handle-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: all 0.2s;
  box-shadow: 0 0 0 0 rgba(64, 158, 255, 0);
}

.port-handle.active .handle-dot,
.port-handle.connecting .handle-dot {
  width: 10px;
  height: 10px;
  box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.2);
}

.port-handle.invalid .handle-dot {
  box-shadow: 0 0 0 4px rgba(245, 108, 108, 0.2);
}

.handle-label {
  font-size: 12px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 已连接的输入端口 */
.port-handle.connected.position-left {
  cursor: pointer;
}

.port-handle.connected.position-left .handle-dot {
  box-shadow: 0 0 0 2px rgba(230, 162, 60, 0.3);
}

.port-handle.connected.position-left:hover .handle-dot {
  background-color: #f56c6c !important;
  box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.3);
}

.port-handle.connected.position-left:hover .handle-label {
  color: #f56c6c;
}
</style>
