<template>
  <div style="display:none"><!-- reactive layer manager --></div>
</template>

<script setup lang="ts">
import { watch, inject, onUnmounted, ref } from 'vue'
import L from 'leaflet'
import { storeToRefs } from 'pinia'
import { useParcelStore } from '@/stores/parcelStore'
import type { Parcel } from '@/models'

const getMap = inject<() => L.Map | null>('leafletMap', () => null)
const parcelStore = useParcelStore()
const { parcels, selectedParcelId } = storeToRefs(parcelStore)
const layerMap = new Map<string, L.GeoJSON>()

function fitToParcel(parcel: Parcel) {
  const map = getMap()
  if (!map) return
  const geojson = parcel.geojson as Record<string, unknown> | undefined
  const geom = (geojson?.geometry ?? geojson) as Record<string, unknown> | undefined
  const coords = geom?.coordinates as number[][][] | undefined
  if (coords?.[0]) {
    const ring = coords[0]
    const bounds = L.latLngBounds(ring.map(([lon, lat]) => [lat, lon] as L.LatLngExpression))
    map.fitBounds(bounds, { padding: [30, 30] })
  }
}

function renderParcels() {
  const map = getMap()
  if (!map) return

  for (const [id, layer] of layerMap) {
    if (!parcels.value.find(p => p.id === id)) {
      map.removeLayer(layer)
      layerMap.delete(id)
    }
  }

  for (const parcel of parcels.value) {
    if (layerMap.has(parcel.id)) continue
    const isSelected = parcel.id === selectedParcelId.value
    const layer = L.geoJSON(parcel.geojson as GeoJSON.GeoJsonObject, {
      style: {
        color: isSelected ? '#409eff' : '#67c23a',
        weight: isSelected ? 3 : 2,
        fillColor: isSelected ? '#409eff' : '#67c23a',
        fillOpacity: 0.15,
      },
    }).addTo(map)

    layer.bindTooltip(`${parcel.name} (${parcel.area_ha?.toFixed(2) ?? '—'} ha)`, { sticky: true })
    layer.on('click', () => {
      parcelStore.selectParcel(parcel.id)
      fitToParcel(parcel)
    })
    layerMap.set(parcel.id, layer)
  }
}

watch([parcels, selectedParcelId], renderParcels, { deep: true })

onUnmounted(() => {
  const map = getMap()
  for (const [, layer] of layerMap) {
    map?.removeLayer(layer)
  }
  layerMap.clear()
})
</script>
