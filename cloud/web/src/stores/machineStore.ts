import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Machine } from '@/models'
import { listMachines } from '@/services/machineApi'

export const useMachineStore = defineStore('machine', () => {
  const machines = ref<Machine[]>([])
  const loading = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const onlineCount  = computed(() => machines.value.filter(m => m.status !== 'offline').length)
  const busyCount    = computed(() => machines.value.filter(m => m.status === 'busy').length)
  const offlineCount = computed(() => machines.value.filter(m => m.status === 'offline').length)

  async function fetchMachines() {
    try {
      machines.value = await listMachines()
    } catch (_) { /* ignore poll errors */ }
  }

  function startPolling(intervalMs = 5000) {
    stopPolling()
    fetchMachines()
    pollTimer = setInterval(fetchMachines, intervalMs)
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  return { machines, loading, onlineCount, busyCount, offlineCount,
           fetchMachines, startPolling, stopPolling }
})
