import { hostApi } from './client'
import type {
  ApiResult,
  Conversation,
  ConversationDetail,
  Message,
  QuestionResolutionInput,
  ReportGenerationSession,
} from '../../types'

export interface PostMessageInput {
  text: string
  templateFile?: File
  dataFile?: File
  /** Decisions about a chapter's missing metrics, submitted from the question card. */
  resolutions?: QuestionResolutionInput[]
}

export const conversationApi = {
  create(title?: string): Promise<ApiResult<Conversation>> {
    return hostApi.post<Conversation>('/conversations', { title: title ?? null })
  },

  list(): Promise<ApiResult<Conversation[]>> {
    return hostApi.get<Conversation[]>('/conversations')
  },

  get(conversationId: string): Promise<ApiResult<ConversationDetail>> {
    return hostApi.get<ConversationDetail>(`/conversations/${conversationId}`)
  },

  remove(conversationId: string): Promise<ApiResult<{ deleted: boolean }>> {
    return hostApi.delete<{ deleted: boolean }>(`/conversations/${conversationId}`)
  },

  /** Stop the run in progress. Finished chapters are kept, so it can be resumed. */
  cancel(conversationId: string): Promise<ApiResult<ReportGenerationSession>> {
    return hostApi.post<ReportGenerationSession>(`/conversations/${conversationId}/cancel`, {})
  },

  /** The only write path: text plus optional uploads, as one message. */
  postMessage(conversationId: string, input: PostMessageInput): Promise<ApiResult<Message>> {
    const form = new FormData()
    form.append('text', input.text)
    if (input.templateFile) form.append('template_file', input.templateFile)
    if (input.dataFile) form.append('data_file', input.dataFile)
    if (input.resolutions?.length) form.append('resolutions', JSON.stringify(input.resolutions))
    return hostApi.uploadForm<Message>(`/conversations/${conversationId}/messages`, form)
  },
}
