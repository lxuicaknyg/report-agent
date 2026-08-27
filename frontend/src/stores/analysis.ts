import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AnalysisRequest, AnalysisResult, DatasetProfile } from '../types'
import { analysisApi } from '../services/api/analysis'

export const useAnalysisStore = defineStore('analysis', () => {
  const currentProfile = ref<DatasetProfile | null>(null)
  const currentResult = ref<AnalysisResult | null>(null)
  const loadingProfile = ref(false)
  const loadingQuery = ref(false)
  const error = ref<string | null>(null)

  async function runProfile(datasetId: string) {
    loadingProfile.value = true
    error.value = null
    currentProfile.value = null
    try {
      const res = await analysisApi.profileDataset(datasetId)
      if (res.success && res.data) {
        currentProfile.value = res.data
      } else if (res.error) {
        error.value = res.error.message
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loadingProfile.value = false
    }
  }

  async function runQuery(request: AnalysisRequest) {
    loadingQuery.value = true
    error.value = null
    currentResult.value = null
    try {
      const res = await analysisApi.queryDataset(request)
      if (res.success && res.data) {
        currentResult.value = res.data
      } else if (res.error) {
        error.value = res.error.message
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loadingQuery.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  function $reset() {
    currentProfile.value = null
    currentResult.value = null
    loadingProfile.value = false
    loadingQuery.value = false
    error.value = null
  }

  return {
    currentProfile,
    currentResult,
    loadingProfile,
    loadingQuery,
    error,
    runProfile,
    runQuery,
    clearError,
    $reset,
  }
})
