import { apiClient } from './client'
import type { ApiResult, AnalysisRequest, AnalysisResult, DatasetProfile } from '../../types'

export const analysisApi = {
  profileDataset(datasetId: string): Promise<ApiResult<DatasetProfile>> {
    return apiClient.post<DatasetProfile>('/analysis/profile', { dataset_id: datasetId })
  },

  queryDataset(request: AnalysisRequest): Promise<ApiResult<AnalysisResult>> {
    return apiClient.post<AnalysisResult>('/analysis/query', request)
  },
}
