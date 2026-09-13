export interface StatusHandlers {
  onHeartbeat?: (data: HeartbeatEvent) => void
  onTaskStatus?: (data: TaskStatusEvent) => void
  onTaskAck?: (data: TaskAckEvent) => void
  onError?: () => void
}

export interface HeartbeatEvent {
  machine_id: string
  status: 'online' | 'busy' | 'error'
  current_task_id: string | null
  timestamp: number
}

export interface TaskStatusEvent {
  edge_task_id: string
  state: string
  progress_pct: number
  current_node: string | null
  machine_id: string
}

export interface TaskAckEvent {
  edge_task_id: string
  accepted: boolean
  dispatch_id: string
}

export function createStatusStream(handlers: StatusHandlers): EventSource {
  const es = new EventSource('/api/v1/events/status')

  es.addEventListener('heartbeat', (e: MessageEvent) => {
    try { handlers.onHeartbeat?.(JSON.parse(e.data)) } catch (_) { /* ignore */ }
  })
  es.addEventListener('task_status', (e: MessageEvent) => {
    try { handlers.onTaskStatus?.(JSON.parse(e.data)) } catch (_) { /* ignore */ }
  })
  es.addEventListener('task_ack', (e: MessageEvent) => {
    try { handlers.onTaskAck?.(JSON.parse(e.data)) } catch (_) { /* ignore */ }
  })
  es.onerror = () => {
    handlers.onError?.()
  }
  return es
}
