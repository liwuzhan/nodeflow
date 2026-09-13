<template>
  <div style="display:none" />
</template>

<script setup lang="ts">
import { watch, inject, onUnmounted, ref } from 'vue'
import L from 'leaflet'
import { storeToRefs } from 'pinia'
import { useMachineStore } from '@/stores/machineStore'

const getMap = inject<() => L.Map | null>('leafletMap', () => null)
const machineStore = useMachineStore()
const { machines } = storeToRefs(machineStore)
const markerMap = new Map<string, L.CircleMarker>()

const colorMap: Record<string, string> = { online: '#67c23a', busy: '#e6a23c', error: '#f56c6c', offline: '#c0c4cc' }

function renderMarkers() {
  const map = getMap()
  if (!map) return

  for (const [id, marker] of markerMap) {
    if (!machines.value.find(m => m.id === id)) {
      map.removeLayer(marker)
      markerMap.delete(id)
    }
  }

  for (const m of machines.value) {
    if (!m.position_lat || !m.position_lon) continue
    const pos: L.LatLngExpression = [m.position_lat, m.position_lon]
    if (!markerMap.has(m.id)) {
      const color = colorMap[m.status] ?? '#c0c4cc'
      const marker = L.circleMarker(pos, {
        radius: 8, color: color, fillColor: color, fillOpacity: 0.8, weight: 2,
      }).addTo(map)
      marker.bindTooltip(`${m.name} · ${m.status}`, { direction: 'top' })
      markerMap.set(m.id, marker)
    } else {
      markerMap.get(m.id)!.setLatLng(pos)
    }
  }
}

watch(machines, renderMarkers, { deep: true })

onUnmounted(() => {
  const map = getMap()
  for (const [, m] of markerMap) { map?.removeLayer(m) }
  markerMap.clear()
})
</script>
