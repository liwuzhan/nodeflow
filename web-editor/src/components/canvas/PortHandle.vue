<template>
  <div
    class="port-handle"
    :data-port-name="portName"
    :data-port-type="portType"
    :data-position="position"
    :class="[
      positionClass,
      { connecting: isConnecting, active: isActive, invalid: showInvalid },
    ]"
    :title="`${portName} (${portType})`"
    @mousedown.stop="startConnection"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <div class="handle-dot" :style="{ backgroundColor: dotColor }" />
    <span class="handle-label">{{ portName }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { getCompatibilityColor, areTypesCompatible } from '@/services/typeChecker'

interface Props {
  nodeId: string
  portName: string
  portType: string
  position: 'left' | 'right' // 'left' for input, 'right' for output
  index: number // 端口在列表中的序号
}

interface Emits {
  (e: 'startConnect', data: ConnectionStartData): void
  (e: 'endConnect'): void
  (e: 'checkCompatibility', data: CompatibilityCheckData): void
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

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const isActive = ref(false)
const showInvalid = ref(false)
const isConnecting = ref(false)

// 端口CSS类名
const positionClass = computed(() => `position-${props.position}`)

// 点的颜色（根据类型和状态）
const dotColor = computed(() => {
  if (showInvalid.value) {
    return '#f56c6c' // 红色 - 不兼容
  }
  if (isActive.value || isConnecting.value) {
    return '#409eff' // 蓝色 - 活跃/连接中
  }
  if (props.portType === 'any') {
    return '#909399' // 灰色 - any类型
  }
  return '#67c23a' // 绿色 - 正常
})

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
  gap: 6px;
  padding: 4px 6px;
  border-radius: 3px;
  cursor: crosshair;
  transition: all 0.2s;
  user-select: none;
}

.port-handle:hover {
  background-color: rgba(64, 158, 255, 0.1);
}

.port-handle.position-left {
  justify-content: flex-start;
}

.port-handle.position-right {
  justify-content: flex-end;
  flex-direction: row-reverse;
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
  font-size: 11px;
  color: #666;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.port-handle:hover .handle-label {
  color: #333;
  font-weight: 500;
}
</style>
