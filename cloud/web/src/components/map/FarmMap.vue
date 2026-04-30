<template>
  <div ref="mapContainer" class="farm-map"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, provide } from 'vue'
import L from 'leaflet'
import { useMapStore } from '@/stores/mapStore'

const mapContainer = ref<HTMLDivElement>()
let map: L.Map | null = null
const mapStore = useMapStore()

provide('leafletMap', () => map)

onMounted(() => {
  map = L.map(mapContainer.value!, {
    center: mapStore.center,
    zoom: mapStore.zoom,
    zoomControl: true,
  })
  L.tileLayer('https://webst0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=6&x={x}&y={y}&z={z}', {
    subdomains: ['1', '2', '3', '4'],
    maxZoom: 19,
    attribution: '&copy; 高德地图',
  }).addTo(map)

  map.on('moveend', () => {
    mapStore.center = [map!.getCenter().lat, map!.getCenter().lng]
    mapStore.zoom = map!.getZoom()
  })
})

onUnmounted(() => {
  map?.remove()
  map = null
})

defineExpose({ getMap: () => map })
</script>

<style scoped>
.farm-map { width: 100%; height: 100%; min-height: 600px; border-radius: 8px; overflow: hidden; }
</style>
