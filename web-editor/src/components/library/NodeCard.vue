<template>
  <div
    class="node-card"
    draggable="true"
    @dragstart="handleDragStart"
  >
    <div class="card-header">
      <el-icon class="node-icon"><Box /></el-icon>
      <span class="node-name">{{ packageName }}</span>
    </div>

    <div class="card-body">
      <p class="node-description">{{ manifest.description || '无描述' }}</p>
      <div class="node-meta">
        <el-tag size="small" type="info">v{{ manifest.version }}</el-tag>
      </div>
    </div>

    <div class="card-footer">
      <div class="port-info">
        <span class="port-count">
          <el-icon><TopRight /></el-icon>
          {{ outputCount }} 输出
        </span>
        <span class="port-count">
          <el-icon><BottomRight /></el-icon>
          {{ inputCount }} 输入
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NodeManifest } from '@/models'
import { getInputPorts, getOutputPorts } from '@/models'

const props = defineProps<{
  packageName: string
  manifest: NodeManifest
}>()

const inputCount = computed(() => getInputPorts(props.manifest).length)
const outputCount = computed(() => getOutputPorts(props.manifest).length)

function handleDragStart(event: DragEvent) {
  if (!event.dataTransfer) return

  // 设置拖拽数据（里程碑2中将在画布上使用）
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('application/node-package', props.packageName)

  console.log(`Dragging node: ${props.packageName}`)
}
</script>

<style scoped>
.node-card {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px;
  cursor: grab;
  transition: all 0.2s;

  &:hover {
    border-color: #409eff;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
    transform: translateY(-2px);
  }

  &:active {
    cursor: grabbing;
  }
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.node-icon {
  font-size: 18px;
  color: #409eff;
}

.node-name {
  font-weight: 600;
  font-size: 14px;
  color: #333;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-body {
  margin-bottom: 8px;
}

.node-description {
  font-size: 12px;
  color: #666;
  margin: 0 0 8px 0;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.node-meta {
  display: flex;
  gap: 4px;
}

.card-footer {
  border-top: 1px solid #f0f0f0;
  padding-top: 8px;
  margin-top: 8px;
}

.port-info {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #999;
}

.port-count {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
