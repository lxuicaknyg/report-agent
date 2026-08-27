import { apiClient } from './client'
import type { ConversationSession, ExecutionPlan, Task, TaskReportResponse, TaskStep } from '../../types'

export const taskApi = {
  createConversation(title?: string) {
    return apiClient.post<ConversationSession>('/conversations', title ? { title } : {})
  },
  getConversation(id: string) {
    return apiClient.get<ConversationSession>(`/conversations/${id}`)
  },
  getTask(id: string) {
    return apiClient.get<Task>(`/tasks/${id}`)
  },
  getTaskPlan(id: string) {
    return apiClient.get<ExecutionPlan>(`/tasks/${id}/plan`)
  },
  getTaskStep(taskId: string, stepId: string) {
    return apiClient.get<TaskStep>(`/tasks/${taskId}/steps/${stepId}`)
  },
  executeTask(id: string) {
    return apiClient.post<Task>(`/tasks/${id}/execute`)
  },
  getTaskReport(id: string) {
    return apiClient.get<TaskReportResponse>(`/tasks/${id}/report`)
  },
  downloadArtifact(id: string) {
    return apiClient.download(`/tasks/${id}/artifact`)
  },
  cancelTask(id: string) {
    return apiClient.post<Task>(`/tasks/${id}/cancel`)
  },
}
