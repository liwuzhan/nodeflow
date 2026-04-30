import { get, post, put, del } from './api'
import type { Parcel, SplitPreviewRequest, SplitPreviewResponse } from '@/models'

export function listParcels(): Promise<Parcel[]> {
  return get<Parcel[]>('/parcels')
}

export function createParcel(data: { name: string; geojson: unknown }): Promise<Parcel> {
  return post<Parcel>('/parcels', data)
}

export function getParcel(id: string): Promise<Parcel> {
  return get<Parcel>(`/parcels/${id}`)
}

export function updateParcel(id: string, data: Record<string, unknown>): Promise<Parcel> {
  return put<Parcel>(`/parcels/${id}`, data)
}

export function deleteParcel(id: string): Promise<void> {
  return del(`/parcels/${id}`)
}

export function previewSplit(parcelId: string, data: SplitPreviewRequest): Promise<SplitPreviewResponse> {
  return post<SplitPreviewResponse>(`/parcels/${parcelId}/preview-split`, data)
}
