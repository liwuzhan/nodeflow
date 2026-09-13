import { ref, onMounted, onUnmounted } from 'vue'

export interface SSEEvent {
  type: 'heartbeat' | 'task_status' | 'task_ack'
  data: Record<string, unknown>
}

export function useSSE(onEvent: (e: SSEEvent) => void) {
  const connected = ref(false)
  let es: EventSource | null = null

  function connect() {
    es?.close()
    es = new EventSource('/api/v1/events/stream')
    es.onopen = () => { connected.value = true }
    es.onerror = () => {
      connected.value = false
      es?.close()
      setTimeout(connect, 5000)
    }
    const handlers: Record<string, (e: MessageEvent) => void> = {
      heartbeat: (e) => onEvent({ type: 'heartbeat', data: JSON.parse(e.data) }),
      task_status: (e) => onEvent({ type: 'task_status', data: JSON.parse(e.data) }),
      task_ack: (e) => onEvent({ type: 'task_ack', data: JSON.parse(e.data) }),
    }
    for (const [type, fn] of Object.entries(handlers)) {
      es.addEventListener(type, fn)
    }
  }

  onMounted(connect)
  onUnmounted(() => es?.close())

  return { connected }
}
