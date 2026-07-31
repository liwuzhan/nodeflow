import { ref, onMounted, onUnmounted } from 'vue'

export interface SSEEvent {
  type: string
  data: unknown
}

export function useSSE(onEvent: (e: SSEEvent) => void) {
  const connected = ref(false)
  let es: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    if (es) { es.close() }
    es = new EventSource('/api/events/stream')
    es.onopen = () => { connected.value = true }
    es.onerror = () => {
      connected.value = false
      es?.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connect, 5000)
    }
    es.addEventListener('heartbeat', (e) => {
      onEvent({ type: 'heartbeat', data: JSON.parse(e.data) })
    })
    es.addEventListener('task_status', (e) => {
      onEvent({ type: 'task_status', data: JSON.parse(e.data) })
    })
    es.addEventListener('task_ack', (e) => {
      onEvent({ type: 'task_ack', data: JSON.parse(e.data) })
    })
  }

  onMounted(connect)
  onUnmounted(() => {
    es?.close()
    if (reconnectTimer) clearTimeout(reconnectTimer)
  })

  return { connected }
}
