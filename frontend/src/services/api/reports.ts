import { hostApi } from './client'
import type { ApiResult, ReportTemplate, ReportGenerationSession } from '../../types'

export interface PaginatedTemplatesResponse {
  total: number
  has_more: boolean
  items: ReportTemplate[]
}

export interface PaginatedSessionsResponse {
  total: number
  has_more: boolean
  items: ReportGenerationSession[]
}

/**
 * Read-only report access. Reports are created and steered through
 * `conversationApi.postMessage`; nothing here mutates a report session.
 */
export const reportApi = {
  listTemplates(offset = 0, limit = 50): Promise<ApiResult<PaginatedTemplatesResponse>> {
    const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    return hostApi.get<PaginatedTemplatesResponse>(`/reports/templates?${q.toString()}`)
  },

  uploadTemplate(file: File): Promise<ApiResult<ReportTemplate>> {
    return hostApi.upload<ReportTemplate>('/reports/templates', file)
  },

  getTemplate(templateId: string): Promise<ApiResult<ReportTemplate>> {
    return hostApi.get<ReportTemplate>(`/reports/templates/${templateId}`)
  },

  listSessions(offset = 0, limit = 20): Promise<ApiResult<PaginatedSessionsResponse>> {
    const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    return hostApi.get<PaginatedSessionsResponse>(`/reports?${q.toString()}`)
  },

  getSession(sessionId: string): Promise<ApiResult<ReportGenerationSession>> {
    return hostApi.get<ReportGenerationSession>(`/reports/${sessionId}`)
  },

  downloadArtifact(sessionId: string, artifactId: string): Promise<ApiResult<Blob>> {
    return hostApi.download(`/reports/${sessionId}/artifacts/${artifactId}`)
  },
}
