<template>
  <div style="display:none" />
</template>

<script setup lang="ts">
import { watch, inject, onUnmounted } from 'vue'
import L from 'leaflet'
import { storeToRefs } from 'pinia'
import { useParcelStore } from '@/stores/parcelStore'
import { useMapStore } from '@/stores/mapStore'
import type { SubParcel } from '@/models'

const getMap = inject<() => L.Map | null>('leafletMap', () => null)
const parcelStore = useParcelStore()
const mapStore = useMapStore()
const { splitPreview } = storeToRefs(parcelStore)
const { showSplitPreview } = storeToRefs(mapStore)

const COLORS = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9b59b6', '#1abc9c', '#e67e22']
let layers: L.GeoJSON[] = []

function clearLayers() {
  const map = getMap()
  for (const layer of layers) { map?.removeLayer(layer) }
  layers = []
}

function renderSplits(splits: SubParcel[]) {
  const map = getMap()
  if (!map) return
  clearLayers()
  if (!showSplitPreview.value) return

  for (const sp of splits) {
    const color = COLORS[sp.index % COLORS.length]
    const layer = L.geoJSON(sp.geojson as GeoJSON.GeoJsonObject, {
      style: {
        color, weight: 2, fillColor: color, fillOpacity: 0.25,
      },
    }).addTo(map)

    const label = `${sp.name}${sp.assigned_machine ? ' → ' + sp.assigned_machine : ''}`
    layer.bindTooltip(label, { permanent: true, direction: 'center', className: 'split-label' })
    layers.push(layer)
  }

  if (splits.length > 0) {
    const allCoords: L.LatLngExpression[] = []
    for (const sp of splits) {
      const geojson = sp.geojson as Record<string, unknown>
      const geom = (geojson?.geometry ?? geojson) as Record<string, unknown>
      const coords = geom?.coordinates as number[][][] | undefined
      if (coords?.[0]) {
        for (const [lon, lat] of coords[0]) {
          allCoords.push([lat, lon])
        }
      }
    }
    if (allCoords.length) {
      map.fitBounds(L.latLngBounds(allCoords), { padding: [40, 40] })
    }
  }
}

watch([splitPreview, showSplitPreview], () => {
  if (splitPreview.value.length > 0 && showSplitPreview.value) {
    renderSplits(splitPreview.value)
  } else {
    clearLayers()
  }
})

onUnmounted(() => clearLayers())
</script>

<style>
.split-label {
  background: rgba(0,0,0,0.7) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 4px !important;
  padding: 2px 8px !important;
  font-size: 12px !important;
}
</style>
