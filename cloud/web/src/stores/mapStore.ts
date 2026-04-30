import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMapStore = defineStore('map', () => {
  const center = ref<[number, number]>([28.91685, 120.037328])
  const zoom = ref(16)
  const showParcels = ref(true)
  const showSplitPreview = ref(false)
  const showMachines = ref(true)

  return { center, zoom, showParcels, showSplitPreview, showMachines }
})
