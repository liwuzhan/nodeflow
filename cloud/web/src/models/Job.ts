export interface Job {
  id: string
  name: string
  parcel_id: string
  status: string
  split_mode: string
  split_count: number
  created_at: string | null
  steps: JobStep[]
}

export interface JobDetail extends Job {
  splits: SubParcelInfo[]
  edge_tasks: EdgeTaskSummary[]
}

export interface JobStep {
  id: string
  seq_index: number
  operation_type: string
  preset_yaml: string
  depends_on: number | null
  status: string
}

export interface JobStepCreate {
  operation_type: string
  preset_yaml: string
  seq_index: number
  depends_on?: number | null
}

export interface JobCreate {
  name?: string
  parcel_id: string
  split_mode: string
  split_count: number
  steps: JobStepCreate[]
  machine_assignments?: Record<string, string>
}

export interface SubParcelInfo {
  index: number
  name: string
  area_ha: number
  assigned_to: string | null
}

export interface EdgeTaskSummary {
  id: string
  edge_task_id: string
  machine_id: string
  state: string
  progress_pct: number
  error_code: string | null
}
