import { hostApi } from './client'
import type {
  AnalysisSqlResult,
  AnalysisType,
  ApiResult,
  ConnectionInput,
  ConnectionQueryResult,
  ConnectionTestResult,
  SupplementShape,
  DataConnection,
  DriverSpec,
} from '../../types'

export const connectionApi = {
  listDrivers(): Promise<ApiResult<DriverSpec[]>> {
    return hostApi.get<DriverSpec[]>('/connections/drivers')
  },

  list(): Promise<ApiResult<DataConnection[]>> {
    return hostApi.get<DataConnection[]>('/connections')
  },

  create(input: ConnectionInput): Promise<ApiResult<DataConnection>> {
    return hostApi.post<DataConnection>('/connections', input)
  },

  update(connectionId: string, input: ConnectionInput): Promise<ApiResult<DataConnection>> {
    return hostApi.put<DataConnection>(`/connections/${connectionId}`, input)
  },

  remove(connectionId: string): Promise<ApiResult<{ deleted: boolean }>> {
    return hostApi.delete<{ deleted: boolean }>(`/connections/${connectionId}`)
  },

  test(connectionId: string): Promise<ApiResult<ConnectionTestResult>> {
    return hostApi.post<ConnectionTestResult>(`/connections/${connectionId}/test`, {})
  },

  /** Trial-run a read-only statement. Rejected SQL resolves successfully with
   * `success: false` on the payload; only an unknown connection is an error. */
  query(
    connectionId: string,
    query: string,
    shape: SupplementShape = 'value',
  ): Promise<ApiResult<ConnectionQueryResult>> {
    return hostApi.post<ConnectionQueryResult>(`/connections/${connectionId}/query`, {
      query,
      shape,
    })
  },

  /** Rewrite a working query into a year-on-year / period-on-period one.
   * Generates only; running it is a separate, explicit step. */
  analysisSql(
    connectionId: string,
    sql: string,
    analysisType: AnalysisType,
  ): Promise<ApiResult<AnalysisSqlResult>> {
    return hostApi.post<AnalysisSqlResult>(`/connections/${connectionId}/analysis-sql`, {
      sql,
      analysis_type: analysisType,
    })
  },
}
