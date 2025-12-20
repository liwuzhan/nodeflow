<template>
  <div
    class="custom-node"
    :data-node-id="node.id"
    :class="{ selected: isSelected, error: hasErrors }"
    :style="{ left: node.position.x + 'px', top: node.position.y + 'px' }"
    @mousedown="handleMouseDown"
    @click.stop="() => $emit('select')"
  >
    <!-- 节点标题栏 -->
    <div class="node-header">
      <div class="node-title">
        <el-icon class="node-icon"><Box /></el-icon>
        <span class="node-name">{{ node.package }}</span>
        <span class="node-id">{{ node.id }}</span>
      </div>
      <el-icon
        class="delete-btn"
        @click.stop="() => $emit('delete')"
      >
        <Close />
      </el-icon>
    </div>

    <!-- 输入端口（左侧） -->
    <div class="ports-section inputs">
      <div class="ports-label">输入</div>
      <div class="ports-list">
        <PortHandle
          v-for="(port, index) in inputPorts"
          :key="`in_${port.name}`"
          :node-id="node.id"
          :port-name="port.name"
          :port-type="port.type || 'any'"
          position="left"
          :index="index"
          @start-connect="$emit('startConnect', $event)"
        />
      </div>
    </div>

    <!-- 输出端口（右侧） -->
    <div class="ports-section outputs">
      <div class="ports-label">输出</div>
      <div class="ports-list">
        <PortHandle
          v-for="(port, index) in outputPorts"
          :key="`out_${port.name}`"
          :node-id="node.id"
          :port-name="port.name"
          :port-type="port.type || 'any'"
          position="right"
          :index="index"
          @start-connect="$emit('startConnect', $event)"
        />
      </div>
    </div>

    <!-- 节点参数概览 -->
    <div v-if="manifest && manifest.params" class="node-params">
      <div class="params-label">参数</div>
      <div class="params-list">
        <div v-for="(schema, key) in manifest.params" :key="key" class="param-item">
          <span class="param-name">{{ key }}</span>
          <span v-if="schema.required" class="required">*</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useNodeLibraryStore } from '@/stores/nodeLibrary'
import { getInputPorts, getOutputPorts } from '@/models'
import type { NodeInstanceUI } from '@/models/RuntimeConfig'
import type { ConnectionStartData } from './PortHandle.vue'
import PortHandle from './PortHandle.vue'

interface Props {
  nodeId: string
  node: NodeInstanceUI
  isSelected: boolean
}

interface Emits {
  (e: 'select'): void
  (e: 'updatePosition', pos: { x: number; y: number }): void
  (e: 'delete'): void
  (e: 'startConnect', data: ConnectionStartData): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const nodeLibraryStore = useNodeLibraryStore()

const manifest = computed(() => nodeLibraryStore.getManifest(props.node.package))

const inputPorts = computed(() => {
  return manifest.value ? getInputPorts(manifest.value) : []
})

const outputPorts = computed(() => {
  return manifest.value ? getOutputPorts(manifest.value) : []
})

const hasErrors = computed(() => props.node.validationErrors.length > 0)

let isDragging = false
let dragStartX = 0
let dragStartY = 0
let startNodeX = 0
let startNodeY = 0

function handleMouseDown(e: MouseEvent) {
  // 不在标题栏上才能拖拽
  if ((e.target as HTMLElement).closest('.delete-btn')) {
    return
  }

  isDragging = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  startNodeX = props.node.position.x
  startNodeY = props.node.position.y

  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)
}

function handleMouseMove(e: MouseEvent) {
  if (!isDragging) return

  const deltaX = e.clientX - dragStartX
  const deltaY = e.clientY - dragStartY

  const newX = startNodeX + deltaX
  const newY = startNodeY + deltaY

  emit('updatePosition', { x: newX, y: newY })
}

function handleMouseUp() {
  isDragging = false
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', handleMouseUp)
}
</script>

<style scoped>
.custom-node {
  position: absolute;
  min-width: 200px;
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  user-select: none;
  transition: all 0.2s;
  cursor: grab;

  &:hover {
    border-color: #409eff;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  &.selected {
    border-color: #409eff;
    border-width: 3px;
    box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.1);
  }

  &.error {
    border-color: #f56c6c;

    &.selected {
      box-shadow: 0 0 0 4px rgba(245, 108, 108, 0.1);
    }
  }

  &:active {
    cursor: grabbing;
  }
}

.node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e0e0e0;
  border-radius: 6px 6px 0 0;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }
}

.node-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.node-icon {
  color: #409eff;
  flex-shrink: 0;
}

.node-name {
  font-weight: 600;
  font-size: 13px;
  color: #333;
  white-space: nowrap;
}

.node-id {
  font-size: 11px;
  color: #999;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-btn {
  cursor: pointer;
  color: #999;
  transition: color 0.2s;

  &:hover {
    color: #f56c6c;
  }
}

.ports-section {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;

  &:last-child {
    border-bottom: none;
  }
}

.ports-label {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
}

.ports-list {
  display: flex;
  flex-direction: column;
}

.port {
  display: flex;
  align-items: center;
  padding: 4px 12px;
  font-size: 12px;
  gap: 8px;

  &:hover {
    background-color: #f5f7fa;
  }
}

.input-port {
  justify-content: flex-start;
}

.output-port {
  justify-content: flex-end;
  flex-direction: row-reverse;
}

.port-handle {
  width: 8px;
  height: 8px;
  background-color: #409eff;
  border-radius: 50%;
  flex-shrink: 0;
  cursor: crosshair;

  &:hover {
    background-color: #66b1ff;
    box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.2);
  }
}

.port-name {
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-params {
  padding: 8px 0;
}

.params-label {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
}

.params-list {
  display: flex;
  flex-direction: column;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  font-size: 12px;
  color: #666;

  &:hover {
    background-color: #f5f7fa;
  }
}

.param-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.required {
  color: #f56c6c;
  font-weight: 600;
}
</style>
