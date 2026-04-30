import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Job, JobDetail, JobCreate } from '@/models'
import { listJobs, createJob, getJob, dispatchJob, cancelJob, deleteJob } from '@/services/jobApi'

export const useJobStore = defineStore('job', () => {
  const jobs = ref<Job[]>([])
  const currentJob = ref<JobDetail | null>(null)
  const loading = ref(false)

  const activeJobs = computed(() => jobs.value.filter(j => j.status === 'running'))

  async function fetchJobs(status?: string) {
    loading.value = true
    try {
      jobs.value = await listJobs(status ? { status } : undefined)
    } finally {
      loading.value = false
    }
  }

  async function fetchJobDetail(jobId: string) {
    currentJob.value = await getJob(jobId)
    return currentJob.value
  }

  async function addJob(data: JobCreate) {
    const job = await createJob(data)
    jobs.value.unshift(job)
    return job
  }

  async function dispatch(jobId: string) {
    return await dispatchJob(jobId)
  }

  async function cancel(jobId: string) {
    return await cancelJob(jobId)
  }

  async function removeJob(jobId: string) {
    await deleteJob(jobId)
    jobs.value = jobs.value.filter(j => j.id !== jobId)
  }

  function updateTaskProgress(edgeTaskId: string, state: string, progressPct: number, currentNode: string | null) {
    if (currentJob.value?.edge_tasks) {
      const t = currentJob.value.edge_tasks.find(et => et.edge_task_id === edgeTaskId)
      if (t) {
        t.state = state
        t.progress_pct = progressPct
      }
    }
  }

  return { jobs, currentJob, loading, activeJobs,
           fetchJobs, fetchJobDetail, addJob, dispatch, cancel, removeJob, updateTaskProgress }
})
