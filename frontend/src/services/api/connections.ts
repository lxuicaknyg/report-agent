import { apiClient } from './client'
import type {
  ApiResult,
  ConnectionInput,
  ConnectionTestResult,
  DataConnection,
  DriverSpec,
} from '../../types'

export const connectionApi = {
  listDrivers(): Promise<ApiResult<DriverSpec[]>> {
    return apiClient.get<DriverSpec[]>('/connections/drivers')
  },

  list(): Promise<ApiResult<DataConnection[]>> {
    return apiClient.get<DataConnection[]>('/connections')
  },

  create(input: ConnectionInput): Promise<ApiResult<DataConnection>> {
    return apiClient.post<DataConnection>('/connections', input)
  },

  update(connectionId: string, input: ConnectionInput): Promise<ApiResult<DataConnection>> {
    return apiClient.put<DataConnection>(`/connections/${connectionId}`, input)
  },

  remove(connectionId: string): Promise<ApiResult<{ deleted: boolean }>> {
    return apiClient.delete<{ deleted: boolean }>(`/connections/${connectionId}`)
  },

  test(connectionId: string): Promise<ApiResult<ConnectionTestResult>> {
    return apiClient.post<ConnectionTestResult>(`/connections/${connectionId}/test`, {})
  },
}
