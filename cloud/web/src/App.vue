<template>
  <CloudLayout />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useMachineStore } from '@/stores/machineStore'
import { useParcelStore } from '@/stores/parcelStore'
import { useJobStore } from '@/stores/jobStore'
import { createStatusStream } from '@/services/statusStream'
import type { HeartbeatEvent, TaskStatusEvent } from '@/services/statusStream'
import CloudLayout from '@/components/layout/CloudLayout.vue'

const machineStore = useMachineStore()
const parcelStore = useParcelStore()
const jobStore = useJobStore()

let es: EventSource | null = null

function connectSSE() {
  es = createStatusStream({
    onHeartbeat(data: HeartbeatEvent) {
      const m = machineStore.machines.find(m => m.id === data.machine_id)
      if (m) {
        m.status = data.status
        m.current_task_id = data.current_task_id
      }
    },
    onTaskStatus(data: TaskStatusEvent) {
      jobStore.updateTaskProgress(data.edge_task_id, data.state, data.progress_pct, data.current_node)
    },
    onError() {
      es?.close()
      setTimeout(connectSSE, 3000)
    },
  })
}

onMounted(() => {
  machineStore.startPolling(10000)
  parcelStore.fetchParcels()
  connectSSE()
})

onUnmounted(() => {
  machineStore.stopPolling()
  es?.close()
})
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
</style>
