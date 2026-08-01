import { reactive } from 'vue'
import { fetchParcels, fetchParcelDetail, fetchMachines, fetchJobs, fetchJobTasks, type Machine, type Parcel, type Job, type EdgeTask } from '../api'

export const store = reactive({
  machines: [] as Machine[],
  parcels: [] as (Parcel & { geojson?: unknown })[],
  jobs: [] as Job[],
  tasks: {} as Record<string, EdgeTask[]>,
  loading: false,

  async refresh() {
    this.loading = true
    try {
      const [machines, parcels, jobs] = await Promise.all([
        fetchMachines(), fetchParcels(), fetchJobs(),
      ])
      this.machines = machines

      // 为每个地块拉取详情（含 GeoJSON）
      const detailed: (Parcel & { geojson?: unknown })[] = []
      for (const p of parcels) {
        try {
          const detail = await fetchParcelDetail(p.id)
          detailed.push({ ...p, geojson: detail.geojson })
        } catch {
          detailed.push(p)
        }
      }
      this.parcels = detailed
      this.jobs = jobs

      for (const j of jobs) {
        if (j.status === 'running') {
          try {
            this.tasks[j.id] = await fetchJobTasks(j.id)
          } catch { /* ignore */ }
        }
      }
    } finally {
      this.loading = false
    }
  },

  updateHeartbeat(data: Record<string, unknown>) {
    const mid = data.machine_id as string
    const m = this.machines.find(x => x.id === mid)
    if (m) {
      if (data.position_lat != null) m.position_lat = data.position_lat as number
      if (data.position_lon != null) m.position_lon = data.position_lon as number
      m.last_heartbeat = new Date().toISOString()
      m.seconds_since_heartbeat = 0
      if (data.cpu_pct != null) m.cpu_pct = data.cpu_pct as number
      if (data.memory_mb != null) m.memory_mb = data.memory_mb as number
    }
  },

  updateTaskStatus(data: Record<string, unknown>) {
    const jobId = data.job_id as string
    if (!jobId || !this.tasks[jobId]) return
    const task = this.tasks[jobId].find(t => t.edge_task_id === data.edge_task_id)
    if (task) {
      task.state = data.state as string
      if (data.progress_pct != null) task.progress_pct = data.progress_pct as number
    }
  },

  getTasksForParcel(parcelId: string): EdgeTask[] {
    const result: EdgeTask[] = []
    for (const jobId of Object.keys(this.tasks)) {
      const job = this.jobs.find(j => j.id === jobId)
      if (job && job.parcel_id === parcelId) {
        result.push(...this.tasks[jobId])
      }
    }
    return result
  },

  getParcelProgress(parcelId: string): number | null {
    const tasks = this.getTasksForParcel(parcelId)
    if (tasks.length === 0) return null
    const completed = tasks.filter(t => t.state === 'completed').length
    return Math.round((completed / tasks.length) * 100)
  },

  getParcelStatus(parcelId: string): string {
    const progress = this.getParcelProgress(parcelId)
    if (progress === null) return 'idle'
    if (progress === 100) return 'completed'
    return 'working'
  },
})
