import { reactive } from 'vue'
import { fetchParcels, fetchMachines, fetchJobs, fetchJobTasks, type Machine, type Parcel, type Job, type EdgeTask } from '../api'

export const store = reactive({
  machines: [] as Machine[],
  parcels: [] as Parcel[],
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
      this.parcels = parcels
      this.jobs = jobs

      // 拉取每个运行中作业的任务
      for (const j of jobs) {
        if (j.status === 'running') {
          const tasks = await fetchJobTasks(j.id)
          this.tasks[j.id] = tasks
        }
      }
    } finally {
      this.loading = false
    }
  },

  updateHeartbeat(data: { machine_id: string; lat?: number; lon?: number; heading?: number; cpu_pct?: number; memory_pct?: number }) {
    const m = this.machines.find(x => x.id === data.machine_id)
    if (m) {
      if (data.lat != null) m.lat = data.lat
      if (data.lon != null) m.lon = data.lon
      if (data.heading != null) m.heading = data.heading
      if (data.cpu_pct != null) m.cpu_pct = data.cpu_pct
      if (data.memory_pct != null) m.memory_pct = data.memory_pct
      m.last_heartbeat = Date.now() / 1000
      m.seconds_since_heartbeat = 0
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
