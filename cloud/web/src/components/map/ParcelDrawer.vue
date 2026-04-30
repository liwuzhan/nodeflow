<template>
  <div style="display:none" />
</template>

<script setup lang="ts">
import { inject, ref, onUnmounted, watch } from 'vue'
import L from 'leaflet'

const props = defineProps<{ active: boolean }>()
const emit = defineEmits<{
  created: [geojson: unknown]
  cancel: []
}>()

const getMap = inject<() => L.Map | null>('leafletMap', () => null)
let markers: L.CircleMarker[] = []
let polygon: L.Polygon | null = null
let clickHandler: L.LeafletEventHandlerFn | undefined
let dblClickHandler: L.LeafletEventHandlerFn | undefined

function clear() {
  const map = getMap()
  for (const m of markers) map?.removeLayer(m)
  if (polygon) map?.removeLayer(polygon)
  markers = []
  polygon = null
}

function startDrawing() {
  const map = getMap()
  if (!map) return
  clear()
  map.getContainer().style.cursor = 'crosshair'

  clickHandler = (e: L.LeafletEvent) => {
    const me = e as L.LeafletMouseEvent
    const { lat, lng } = me.latlng
    const marker = L.circleMarker([lat, lng], {
      radius: 5, color: '#409eff', fillColor: '#409eff', fillOpacity: 0.8,
    }).addTo(map!)
    markers.push(marker)

    if (markers.length >= 3) {
      const latlngs = markers.map(m => m.getLatLng())
      if (polygon) map!.removeLayer(polygon)
      polygon = L.polygon(latlngs, {
        color: '#409eff', weight: 2, fillColor: '#409eff', fillOpacity: 0.15,
      }).addTo(map!)
    }
  }

  dblClickHandler = () => finishDrawing()

  map.on('click', clickHandler)
  map.on('dblclick', dblClickHandler)
}

function finishDrawing() {
  const map = getMap()
  if (!map) return
  map.getContainer().style.cursor = ''
  map.off('click', clickHandler!)
  map.off('dblclick', dblClickHandler!)
  clickHandler = undefined
  dblClickHandler = undefined

  if (markers.length < 3) {
    clear()
    emit('cancel')
    return
  }

  const latlngs = markers.map(m => m.getLatLng())
  const coords = latlngs.map(ll => [ll.lng, ll.lat])
  coords.push(coords[0])  // close ring

  emit('created', {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [coords] },
    properties: {},
  })

  clear()
}

function cancel() {
  const map = getMap()
  if (!map) return
  map.getContainer().style.cursor = ''
  if (clickHandler) map.off('click', clickHandler)
  if (dblClickHandler) map.off('dblclick', dblClickHandler)
  clickHandler = undefined
  dblClickHandler = undefined
  clear()
}

watch(() => props.active, (val) => {
  if (val) startDrawing()
  else cancel()
})

onUnmounted(() => cancel())
</script>
