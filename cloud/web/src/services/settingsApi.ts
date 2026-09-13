import { get, put } from './api'

export interface CoordinateFrame {
  ready: boolean
  type: 'ENU'
  frame_id: string | null
  origin_source: string | null
  ref_lon: number | null
  ref_lat: number | null
  ref_alt: number | null
  revision: number | null
  updated_at: string | null
}

export interface CoordinateFrameUpdate {
  frame_id: string
  origin_source: 'rtk_base_manual' | 'first_fixed_position'
  ref_lon: number
  ref_lat: number
  ref_alt: number | null
}

export function getCoordinateFrame(): Promise<CoordinateFrame> {
  return get<CoordinateFrame>('/settings/coordinate-frame')
}

export function updateCoordinateFrame(data: CoordinateFrameUpdate): Promise<CoordinateFrame> {
  return put<CoordinateFrame>('/settings/coordinate-frame', data)
}
