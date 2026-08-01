const BASE = '/api/v1'

export interface Machine {
  id: string
  name: string
  status: 'online' | 'offline' | 'busy' | 'error' | 'unregistered'
  last_heartbeat: string | null
  position_lat: number | null
  position_lon: number | null
  cpu_pct: number
  memory_mb: number
  seconds_since_heartbeat: number | null
  current_task_id: string | null
}

export interface Parcel {
  id: string
  name: string
  area_hectares: number | null
}

export interface Job {
  id: string
  name: string
  parcel_id: string
  status: string
  created_at?: string
  steps?: { seq_index: number; operation_type: string; status: string }[]
}

export interface EdgeTask {
  id: string
  edge_task_id: string
  machine_id: string
  state: string
  progress_pct?: number
}

async function request<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  const body = await r.json()
  return body.data ?? body
}

export async function fetchParcels(): Promise<Parcel[]> {
  return request<Parcel[]>('/parcels')
}

export async function fetchParcelDetail(id: string): Promise<Parcel & { geojson?: unknown }> {
  return request(`/parcels/${id}`)
}

export async function fetchMachines(): Promise<Machine[]> {
  return request<Machine[]>('/machines')
}

export async function fetchJobs(): Promise<Job[]> {
  return request<Job[]>('/jobs')
}

export async function fetchJobDetail(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}`)
}

export async function fetchJobTasks(jobId: string): Promise<EdgeTask[]> {
  return request<EdgeTask[]>(`/jobs/${jobId}/tasks`)
}
