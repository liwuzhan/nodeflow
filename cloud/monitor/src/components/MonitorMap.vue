<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import L from 'leaflet'
import { store } from '../stores/monitorStore'

const mapContainer = ref<HTMLDivElement>()
let map: L.Map | null = null
let parcelLayers: L.GeoJSON[] = []
let machineMarkers: Map<string, L.CircleMarker> = new Map()

onMounted(() => {
  map = L.map(mapContainer.value!, {
    center: [35.0, 115.0], zoom: 14,
    zoomControl: false, attributionControl: false,
  })
  L.tileLayer('https://webst0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=6&x={x}&y={y}&z={z}', {
    subdomains: ['1', '2', '3', '4'], maxZoom: 19,
  }).addTo(map)
  L.control.zoom({ position: 'bottomright' }).addTo(map)
  renderAll()
})

onUnmounted(() => { map?.remove(); parcelLayers.forEach(l => l.remove()) })

function parcelColor(status: string): string {
  if (status === 'completed') return '#22c55e'
  if (status === 'working') return '#f59e0b'
  return 'rgba(148,163,184,0.3)'
}

function renderAll() {
  parcelLayers.forEach(l => l.remove()); parcelLayers = []
  for (const p of store.parcels) {
    if (!p.geojson) continue
    const status = store.getParcelStatus(p.id)
    const progress = store.getParcelProgress(p.id)
    const layer = L.geoJSON(p.geojson as any, {
      style: { fillColor: parcelColor(status), fillOpacity: status === 'idle' ? 0.15 : 0.35, color: parcelColor(status), weight: 2, opacity: 0.8 },
    }).addTo(map!)
    try {
      const center = L.geoJSON(p.geojson as any).getBounds().getCenter()
      let label = p.name || ''
      if (progress !== null) label += ` ${progress}%`
      L.marker(center, {
        icon: L.divIcon({ className: 'parcel-label', html: `<span>${label}</span>`, iconSize: [120, 24], iconAnchor: [60, 12] }),
      }).addTo(map!)
    } catch { /* ignore */ }
    parcelLayers.push(layer)
  }

  for (const m of store.machines) {
    const lat = m.position_lat, lon = m.position_lon
    if (lat == null || lon == null) continue
    const color = m.status === 'online' ? '#3b82f6' : m.status === 'busy' ? '#f59e0b' : '#6b7280'
    if (machineMarkers.has(m.id)) {
      const marker = machineMarkers.get(m.id)!
      marker.setLatLng([lat, lon])
      marker.setStyle({ fillColor: color })
    } else {
      const marker = L.circleMarker([lat, lon], {
        radius: 10, fillColor: color, fillOpacity: 0.9, color: '#fff', weight: 2,
      }).addTo(map!)
      marker.bindTooltip(m.name || m.id, { permanent: true, direction: 'top', offset: [0, -14] })
      machineMarkers.set(m.id, marker)
    }
  }
}

watch(() => store.parcels, renderAll, { deep: true })
watch(() => store.machines, renderAll, { deep: true })
watch(() => store.tasks, renderAll, { deep: true })
</script>

<template><div ref="mapContainer" class="monitor-map"></div></template>

<style>
.monitor-map { width: 100%; height: 100%; }
.parcel-label span { background: rgba(0,0,0,0.7); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; white-space: nowrap; }
.monitor-map .leaflet-tooltip { background: rgba(0,0,0,0.75); color: #fff; border: none; border-radius: 4px; padding: 2px 6px; font-size: 11px; }
</style>
