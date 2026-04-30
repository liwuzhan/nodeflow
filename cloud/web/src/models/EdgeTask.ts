export interface EdgeTask {
  id: string
  edge_task_id: string
  job_id: string
  step_id: string | null
  machine_id: string
  dispatch_id: string | null
  operation_type: string
  seq_index: number
  preset_yaml: string
  state: string
  progress_pct: number
  current_node: string | null
  attempt: number
  dispatched_at: number | null
  completed_at: number | null
  error_code: string | null
  error_detail: string | null
}
