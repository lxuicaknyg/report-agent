import { apiClient } from './client'
import type {
  ApiResult,
  ReportTemplate,
  ReportGenerationSession,
  CreateReportGenerationRequest,
  AnswerReportQuestionRequest,
  ConfirmReportPlanRequest,
  LegacyProfileReportResponse,
} from '../../types'

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

export interface WorkflowIntakeResponse {
  request_id: string
  intent: string
  confidence: number
  status: string
  session: ReportGenerationSession
}

export const reportApi = {
  intakeWorkflow(templateFile: File, dataFile: File, instruction: string, title?: string): Promise<ApiResult<WorkflowIntakeResponse>> {
    const form = new FormData()
    form.append('workflow', 'report_generation')
    form.append('template_file', templateFile)
    form.append('data_file', dataFile)
    form.append('instruction', instruction)
    if (title?.trim()) form.append('title', title.trim())
    return apiClient.uploadForm<WorkflowIntakeResponse>('/reports/workflows/intake', form)
  },

  listTemplates(offset = 0, limit = 50): Promise<ApiResult<PaginatedTemplatesResponse>> {
    const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    return apiClient.get<PaginatedTemplatesResponse>(`/reports/templates?${q.toString()}`)
  },

  uploadTemplate(file: File): Promise<ApiResult<ReportTemplate>> {
    return apiClient.upload<ReportTemplate>('/reports/templates', file)
  },

  getTemplate(templateId: string): Promise<ApiResult<ReportTemplate>> {
    return apiClient.get<ReportTemplate>(`/reports/templates/${templateId}`)
  },

  listSessions(offset = 0, limit = 20): Promise<ApiResult<PaginatedSessionsResponse>> {
    const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    return apiClient.get<PaginatedSessionsResponse>(`/reports?${q.toString()}`)
  },

  createSession(request: CreateReportGenerationRequest): Promise<ApiResult<ReportGenerationSession>> {
    return apiClient.post<ReportGenerationSession>('/reports', request)
  },

  getSession(sessionId: string): Promise<ApiResult<ReportGenerationSession>> {
    return apiClient.get<ReportGenerationSession>(`/reports/${sessionId}`)
  },

  answerQuestion(
    sessionId: string,
    request: AnswerReportQuestionRequest,
  ): Promise<ApiResult<ReportGenerationSession>> {
    return apiClient.post<ReportGenerationSession>(`/reports/${sessionId}/answers`, request)
  },

  resumeSession(sessionId: string): Promise<ApiResult<ReportGenerationSession>> {
    return apiClient.post<ReportGenerationSession>(`/reports/${sessionId}/resume`, {})
  },

   confirmPlan(
    sessionId: string,
    request: ConfirmReportPlanRequest,
  ): Promise<ApiResult<ReportGenerationSession>> {
    return apiClient.post<ReportGenerationSession>(`/reports/${sessionId}/plan/confirm`, request)
  },

  downloadArtifact(sessionId: string, artifactId: string): Promise<ApiResult<Blob>> {
    return apiClient.download(`/reports/${sessionId}/artifacts/${artifactId}`)
  },

  createLegacyDraft(datasetId: string, title?: string): Promise<ApiResult<LegacyProfileReportResponse>> {
    return apiClient.post<LegacyProfileReportResponse>('/reports/draft', {
      dataset_id: datasetId,
      title: title || '',
    })
  },
}

