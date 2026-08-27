import { apiClient } from './client'
import type {
  ApiResult,
  DatasetInfo,
  SheetInfo,
  ColumnSchema,
  DataReadRequest,
  DataReadResult,
  SqlRegisterRequest,
} from '../../types'

export const datasetApi = {
  listDatasets(): Promise<ApiResult<DatasetInfo[]>> {
    return apiClient.get<DatasetInfo[]>('/datasets')
  },

  uploadExcel(file: File): Promise<ApiResult<DatasetInfo>> {
    return apiClient.upload<DatasetInfo>('/datasets/excel', file)
  },

  registerSql(payload: SqlRegisterRequest): Promise<ApiResult<DatasetInfo>> {
    return apiClient.post<DatasetInfo>('/datasets/sql', payload)
  },

  listSheets(datasetId: string): Promise<ApiResult<SheetInfo[]>> {
    return apiClient.get<SheetInfo[]>(`/datasets/${datasetId}/sheets`)
  },

  getSchema(datasetId: string, sheetName?: string | null): Promise<ApiResult<ColumnSchema[]>> {
    const qs = sheetName ? `?sheet_name=${encodeURIComponent(sheetName)}` : ''
    return apiClient.get<ColumnSchema[]>(`/datasets/${datasetId}/schema${qs}`)
  },

  previewDataset(datasetId: string, request: DataReadRequest): Promise<ApiResult<DataReadResult>> {
    return apiClient.post<DataReadResult>(`/datasets/${datasetId}/preview`, request)
  },
}
