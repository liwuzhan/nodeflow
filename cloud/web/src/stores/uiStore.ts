import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const showParcelDrawer = ref(false)

  return { sidebarCollapsed, showParcelDrawer }
})
