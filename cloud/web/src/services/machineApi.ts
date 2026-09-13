import { get, post, del } from './api'
import type { Machine, MachineCreate } from '@/models'

export function listMachines(): Promise<Machine[]> {
  return get<Machine[]>('/machines')
}

export function createMachine(data: MachineCreate): Promise<Machine> {
  return post<Machine>('/machines', data)
}

export function getMachine(id: string): Promise<Machine> {
  return get<Machine>(`/machines/${id}`)
}

export function confirmMachine(id: string): Promise<Machine> {
  return post<Machine>(`/machines/${id}/confirm`)
}

export function deleteMachine(id: string): Promise<void> {
  return del(`/machines/${id}`)
}
