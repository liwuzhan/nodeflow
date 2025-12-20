/**
 * UI状态Store
 * 管理UI交互状态（面板、主题等）
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  // State
  const leftPanelWidth = ref(280)
  const rightPanelWidth = ref(320)
  const rightPanelVisible = ref(true)
  const selectedNodeId = ref<string | null>(null)
  const theme = ref<'light' | 'dark'>('light')

  // Actions
  function setLeftPanelWidth(width: number) {
    leftPanelWidth.value = Math.max(200, Math.min(width, 600))
  }

  function setRightPanelWidth(width: number) {
    rightPanelWidth.value = Math.max(250, Math.min(width, 600))
  }

  function toggleRightPanel() {
    rightPanelVisible.value = !rightPanelVisible.value
  }

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
  }

  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  return {
    leftPanelWidth,
    rightPanelWidth,
    rightPanelVisible,
    selectedNodeId,
    theme,
    setLeftPanelWidth,
    setRightPanelWidth,
    toggleRightPanel,
    selectNode,
    toggleTheme,
  }
})
