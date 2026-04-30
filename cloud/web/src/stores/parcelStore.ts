import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Parcel, SubParcel, SplitPreviewRequest } from '@/models'
import { listParcels, createParcel, deleteParcel, previewSplit } from '@/services/parcelApi'

export const useParcelStore = defineStore('parcel', () => {
  const parcels = ref<Parcel[]>([])
  const selectedParcelId = ref<string | null>(null)
  const splitPreview = ref<SubParcel[]>([])
  const loading = ref(false)

  const selectedParcel = computed(() =>
    parcels.value.find(p => p.id === selectedParcelId.value) ?? null
  )

  async function fetchParcels() {
    loading.value = true
    try {
      parcels.value = await listParcels()
    } finally {
      loading.value = false
    }
  }

  async function addParcel(name: string, geojson: unknown) {
    const p = await createParcel({ name, geojson })
    parcels.value.unshift(p)
    return p
  }

  async function removeParcel(id: string) {
    await deleteParcel(id)
    parcels.value = parcels.value.filter(p => p.id !== id)
    if (selectedParcelId.value === id) selectedParcelId.value = null
  }

  async function fetchSplitPreview(parcelId: string, req: SplitPreviewRequest) {
    const resp = await previewSplit(parcelId, req)
    splitPreview.value = resp.sub_parcels
    return resp.sub_parcels
  }

  function selectParcel(id: string | null) {
    selectedParcelId.value = id
  }

  return { parcels, selectedParcelId, splitPreview, loading, selectedParcel,
           fetchParcels, addParcel, removeParcel, fetchSplitPreview, selectParcel }
})
