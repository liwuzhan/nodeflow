<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { store } from './stores/monitorStore'
import { useSSE } from './composables/useSSE'
import MonitorMap from './components/MonitorMap.vue'
import MachinePanel from './components/MachinePanel.vue'
import StatusBar from './components/StatusBar.vue'

const { connected } = useSSE((e) => {
  if (e.type === 'heartbeat') {
    store.updateHeartbeat(e.data as any)
  }
})

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await store.refresh()
  pollTimer = setInterval(() => store.refresh(), 15000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="monitor-root">
    <MonitorMap />
    <MachinePanel />
    <StatusBar :connected="connected" :machine-count="store.machines.length" />
  </div>
</template>

<style>
.monitor-root {
  width: 100%; height: 100%;
  position: relative;
  background: #1a1a2e;
}
</style>
