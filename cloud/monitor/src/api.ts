const BASE = '/api'

export interface Machine {
  id: string
  name: string
  status: string
  lat?: number
  lon?: number
  heading?: number
  last_heartbeat?: number
  cpu_pct?: number
  memory_pct?: number
  seconds_since_heartbeat?: number
}

export interface Parcel {
  id: string
  name: string
  geojson?: unknown
  area_hectares?: number
}

export interface Job {
  id: string
  name: string
  parcel_id: string
  status: string
  created_at?: number
  steps?: JobStep[]
}

export interface JobStep {
  seq_index: number
  operation_type: string
  status: string
}

export interface EdgeTask {
  id: string
  edge_task_id: string
  machine_id: string
  state: string
  progress_pct?: number
  parcel_split_id?: string
}

export async function fetchParcels(): Promise<Parcel[]> {
  const r = await fetch(`${BASE}/parcels`)
  return r.json()
}

export async function fetchMachines(): Promise<Machine[]> {
  const r = await fetch(`${BASE}/machines`)
  return r.json()
}

export async function fetchJobs(): Promise<Job[]> {
  const r = await fetch(`${BASE}/jobs`)
  return r.json()
}

export async function fetchJobTasks(jobId: string): Promise<EdgeTask[]> {
  const r = await fetch(`${BASE}/jobs/${jobId}/tasks`)
  return r.json()
}
