import { get, post, del } from './api'
import type { Job, JobDetail, JobCreate, EdgeTaskSummary } from '@/models'

export function listJobs(params?: { status?: string; parcel_id?: string }): Promise<Job[]> {
  const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
  return get<Job[]>(`/jobs${qs}`)
}

export function createJob(data: JobCreate): Promise<JobDetail> {
  return post<JobDetail>('/jobs', data)
}

export function getJob(id: string): Promise<JobDetail> {
  return get<JobDetail>(`/jobs/${id}`)
}

export function deleteJob(id: string): Promise<void> {
  return del(`/jobs/${id}`)
}

export function dispatchJob(id: string): Promise<{ dispatched: number; job_id: string; status: string }> {
  return post(`/jobs/${id}/dispatch`)
}

export function cancelJob(id: string): Promise<{ cancelled: number; job_id: string }> {
  return post(`/jobs/${id}/cancel`)
}

export function listJobTasks(jobId: string): Promise<EdgeTaskSummary[]> {
  return get<EdgeTaskSummary[]>(`/jobs/${jobId}/tasks`)
}
