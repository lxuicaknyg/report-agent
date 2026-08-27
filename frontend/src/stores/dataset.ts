import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DatasetInfo } from '../types'
import { datasetApi } from '../services/api/datasets'

export const useDatasetStore = defineStore('dataset', () => {
  const datasets = ref<DatasetInfo[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadDatasets(force = false) {
    if (datasets.value.length > 0 && !force) return
    loading.value = true
    error.value = null
    try {
      const res = await datasetApi.listDatasets()
      if (res.success && res.data) {
        datasets.value = res.data
      } else if (res.error) {
        error.value = res.error.message
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loading.value = false
    }
  }

  function addDataset(ds: DatasetInfo) {
    const idx = datasets.value.findIndex((d) => d.dataset_id === ds.dataset_id)
    if (idx === -1) datasets.value.unshift(ds)
    else datasets.value[idx] = ds
  }

  function clearError() {
    error.value = null
  }

  function $reset() {
    datasets.value = []
    loading.value = false
    error.value = null
  }

  return {
    datasets,
    loading,
    error,
    loadDatasets,
    addDataset,
    clearError,
    $reset,
  }
})
