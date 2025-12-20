<template>
  <div class="app-layout">
    <!-- 顶部工具栏 -->
    <TopToolbar />

    <div class="layout-content">
      <!-- 左侧节点库面板 -->
      <div
        class="left-panel"
        :style="{ width: uiStore.leftPanelWidth + 'px' }"
      >
        <LeftPanel />
      </div>

      <!-- 中间拖拽分割线 -->
      <div
        class="divider"
        @mousedown="startDragLeftDivider"
      ></div>

      <!-- 中央画布区域 -->
      <div class="canvas-area">
        <GraphCanvas />
      </div>

      <!-- 右侧属性编辑面板 -->
      <div
        v-if="uiStore.rightPanelVisible"
        class="right-panel"
        :style="{ width: uiStore.rightPanelWidth + 'px' }"
      >
        <RightPanel />
      </div>

      <!-- 右侧拖拽分割线 -->
      <div
        v-if="uiStore.rightPanelVisible"
        class="divider"
        @mousedown="startDragRightDivider"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useUiStore } from '@/stores/ui'
import TopToolbar from './TopToolbar.vue'
import LeftPanel from './LeftPanel.vue'
import RightPanel from './RightPanel.vue'
import GraphCanvas from '@/components/canvas/GraphCanvas.vue'

const uiStore = useUiStore()
const dragging = ref(false)
const dragType = ref<'left' | 'right' | null>(null)

function startDragLeftDivider() {
  dragging.value = true
  dragType.value = 'left'
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', stopDrag)
}

function startDragRightDivider() {
  dragging.value = true
  dragType.value = 'right'
  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', stopDrag)
}

function handleMouseMove(e: MouseEvent) {
  if (!dragging.value) return

  if (dragType.value === 'left') {
    const newWidth = Math.max(200, Math.min(e.clientX, window.innerWidth - 500))
    uiStore.setLeftPanelWidth(newWidth)
  } else if (dragType.value === 'right') {
    const newWidth = Math.max(250, window.innerWidth - e.clientX)
    uiStore.setRightPanelWidth(newWidth)
  }
}

function stopDrag() {
  dragging.value = false
  dragType.value = null
  document.removeEventListener('mousemove', handleMouseMove)
  document.removeEventListener('mouseup', stopDrag)
}
</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background-color: #f5f5f5;
}

.layout-content {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

.left-panel {
  display: flex;
  flex-direction: column;
  background-color: white;
  border-right: 1px solid #e0e0e0;
  overflow: hidden;
}

.canvas-area {
  flex: 1;
  background-color: #fafafa;
  overflow: hidden;
}

.right-panel {
  display: flex;
  flex-direction: column;
  background-color: white;
  border-left: 1px solid #e0e0e0;
  overflow: hidden;
}

.divider {
  width: 1px;
  background-color: #e0e0e0;
  cursor: col-resize;
  transition: background-color 0.2s;
  user-select: none;

  &:hover {
    background-color: #409eff;
  }
}
</style>
