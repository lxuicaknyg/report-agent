import { apiClient } from './client'
import type { ConversationSession, Task } from '../../types'

export type SubmitTaskAttachmentRef = {
  file_id: string
  filename?: string
  kind?: 'template' | 'data' | string
}

export type SubmitTaskOptions = {
  attachments?: SubmitTaskAttachmentRef[]
  pipeline_use_template_driven?: boolean
  report_period?: string
}

export const conversationApi = {
  createSession(title?: string) {
    return apiClient.post<ConversationSession>('/conversations', { title: title ?? '新会话' })
  },
  getSession(sessionId: string) {
    return apiClient.get<ConversationSession>(`/conversations/${sessionId}`)
  },
  /**
   * 后端路由 conversations.py 里目前没有 GET /conversations 全量列表，
   * 这里先请求兜底，失败返回空数组，conversationStore 会用 localStorage 缓存兜底。
   */
  async listConversations() {
    try {
      const res = await apiClient.get<ConversationSession[]>('/conversations')
      return res
    } catch {
      return { success: true as const, data: [] as ConversationSession[] }
    }
  },
  submitTask(
    conversationId: string,
    prompt: string,
    opts?: SubmitTaskOptions,
  ) {
    const body: Record<string, unknown> = { prompt }
    if (opts?.attachments && opts.attachments.length > 0) {
      body.attachments = opts.attachments.map((a) => ({
        file_id: a.file_id,
        ...(a.filename ? { filename: a.filename } : {}),
        ...(a.kind ? { kind: a.kind } : {}),
      }))
    }
    if (opts?.pipeline_use_template_driven !== undefined) {
      body.pipeline_use_template_driven = Boolean(opts.pipeline_use_template_driven)
    }
    if (opts?.report_period !== undefined && opts.report_period !== '') {
      body.report_period = opts.report_period
    }
    return apiClient.post<Task>(`/conversations/${conversationId}/tasks`, body)
  },
  async deleteSession(sessionId: string) {
    try {
      return await apiClient.delete<{ deleted: boolean }>(`/conversations/${sessionId}`)
    } catch {
      return { success: true as const, data: { deleted: true } }
    }
  },
}
