export interface Machine {
  id: string
  name: string
  machine_type: string
  status: 'online' | 'offline' | 'busy' | 'error' | 'unregistered'
  last_heartbeat: string | null
  current_task_id: string | null
  current_job_id: string | null
  position_lon: number | null
  position_lat: number | null
  cpu_pct: number
  memory_mb: number
  disk_free_gb: number
  runtime_uptime_s: number
  seconds_since_heartbeat: number | null
}

export interface MachineCreate {
  id: string
  name: string
  machine_type?: string
  implement_width_m?: number
}
