<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import L from 'leaflet'
import { store } from '../stores/monitorStore'

const mapContainer = ref<HTMLDivElement>()
let map: L.Map | null = null
let parcelLayers: L.GeoJSON[] = []
let machineMarkers: Map<string, L.CircleMarker> = new Map()

const machineCount = computed(() => store.machines.filter(m => m.status === 'online').length)
const workingCount = computed(() => store.jobs.filter(j => j.status === 'running').length)

onMounted(() => {
  map = L.map(mapContainer.value!, {
    center: [35.0, 115.0],
    zoom: 14,
    zoomControl: false,
    attributionControl: false,
  })

  L.tileLayer('https://webst0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=6&x={x}&y={y}&z={z}', {
    subdomains: ['1', '2', '3', '4'],
    maxZoom: 19,
  }).addTo(map)

  L.control.zoom({ position: 'bottomright' }).addTo(map)

  renderParcels()
  renderMachines()
})

onUnmounted(() => {
  map?.remove()
  parcelLayers.forEach(l => l.remove())
})

function parcelColor(status: string): string {
  switch (status) {
    case 'completed': return '#22c55e'
    case 'working': return '#f59e0b'
    default: return 'rgba(148,163,184,0.3)'
  }
}

function parcelOpacity(status: string): number {
  return status === 'idle' ? 0.15 : 0.35
}

function renderParcels() {
  parcelLayers.forEach(l => l.remove())
  parcelLayers = []

  for (const parcel of store.parcels) {
    if (!parcel.geojson) continue
    const status = store.getParcelStatus(parcel.id)
    const progress = store.getParcelProgress(parcel.id)

    const layer = L.geoJSON(parcel.geojson as any, {
      style: {
        fillColor: parcelColor(status),
        fillOpacity: parcelOpacity(status),
        color: parcelColor(status),
        weight: 2,
        opacity: 0.8,
      },
    }).addTo(map!)

    // 地块中心标签
    try {
      const gj = parcel.geojson as any
      const center = L.geoJSON(gj).getBounds().getCenter()
      let label = parcel.name || ''
      if (progress !== null) label += ` ${progress}%`
      if (label) {
        L.marker(center, {
          icon: L.divIcon({
            className: 'parcel-label',
            html: `<span>${label}</span>`,
            iconSize: [120, 24],
            iconAnchor: [60, 12],
          }),
        }).addTo(map!)
      }
    } catch { /* 忽略标签错误 */ }

    parcelLayers.push(layer)
  }
}

function renderMachines() {
  for (const m of store.machines) {
    if (m.lat == null || m.lon == null) continue

    const color = m.status === 'online' ? '#3b82f6' :
                  m.status === 'working' ? '#f59e0b' : '#6b7280'

    if (machineMarkers.has(m.id)) {
      const marker = machineMarkers.get(m.id)!
      marker.setLatLng([m.lat, m.lon])
      if (m.heading != null) {
        // 更新方向指示
        const icon = L.divIcon({
          className: 'machine-icon',
          html: `<div style="transform:rotate(${m.heading}deg)">▲</div>`,
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        })
        marker.setIcon(icon)
      }
    } else {
      const marker = L.circleMarker([m.lat, m.lon], {
        radius: 10,
        fillColor: color,
        fillOpacity: 0.9,
        color: '#fff',
        weight: 2,
      }).addTo(map!)
      marker.bindTooltip(m.name || m.id, { permanent: true, direction: 'top', offset: [0, -14] })
      machineMarkers.set(m.id, marker)
    }
  }
}

// 响应数据变化
watch(() => store.parcels, renderParcels, { deep: true })
watch(() => store.machines, renderMachines, { deep: true })
watch(() => store.tasks, renderParcels, { deep: true })
</script>

<template>
  <div ref="mapContainer" class="monitor-map"></div>
</template>

<style>
.monitor-map { width: 100%; height: 100%; }
.parcel-label span {
  background: rgba(0,0,0,0.7); color: #fff; padding: 2px 8px;
  border-radius: 4px; font-size: 12px; white-space: nowrap;
}
.machine-icon div {
  color: #3b82f6; font-size: 18px; text-shadow: 0 0 4px rgba(0,0,0,0.5);
  transition: transform 0.3s ease;
}
.monitor-map .leaflet-tooltip {
  background: rgba(0,0,0,0.75); color: #fff; border: none;
  border-radius: 4px; padding: 2px 6px; font-size: 11px;
}
</style>
