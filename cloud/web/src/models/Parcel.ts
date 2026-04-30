export interface Parcel {
  id: string
  name: string
  area_ha: number
  created_at: string | null
  updated_at?: string | null
  geojson?: unknown
  vehicle_cfg?: VehicleConfig
  ref_point?: RefPoint
}

export interface VehicleConfig {
  implement_width_m: number
  overlap_ratio: number
  path_inset_m: number
}

export interface RefPoint {
  lon: number
  lat: number
}

export interface SubParcel {
  index: number
  name: string
  geojson: unknown
  area_ha: number
  assigned_machine: string | null
}

export interface SplitPreviewRequest {
  mode: string
  count: number
  angle_deg?: number | null
  machine_assignments?: Record<string, string>
}

export interface SplitPreviewResponse {
  sub_parcels: SubParcel[]
}
