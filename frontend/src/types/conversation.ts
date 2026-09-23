import type { ReportArtifact, ReportGenerationSession, ReportPlan, UserQuestion } from './report'

export type MessageRole = 'user' | 'assistant'
export type MessageKind = 'text' | 'plan' | 'progress' | 'question' | 'report' | 'error'
export type AttachmentKind = 'template' | 'data'

export interface MessageAttachment {
  filename: string
  kind: AttachmentKind
  size: number
}

export interface PlanMessagePayload {
  session_id: string
  plan: ReportPlan
}

export type ChapterProgressStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'waiting_user'
  /** 跑被停掉或失败时停在的那一章，说「继续」会从这里接着写。 */
  | 'stopped'

export interface ProgressChapter {
  section_id: string
  title: string
  completed: boolean
  status?: ChapterProgressStatus
  content?: string
}

/** One decision the user made about a missing metric. */
export interface QuestionResolutionInput {
  question_id: string
  action: 'value' | 'sql' | 'table' | 'drop'
  value?: string
  note?: string
  /** Set for `action: 'sql'` only. The backend re-runs the statement and reads
   * the value out of it, so no value is sent for this action. */
  connection_id?: string
  query?: string
  /** Set for `action: 'table'` only: the rows as they were pasted. The backend
   * parses them, so what lands in the report is the same read of the same text
   * the preview showed. */
  text?: string
  /** Says this question was classified wrongly: it was raised as a single
   * figure and is being answered with a list. How a query is read comes from
   * the question, not from a mode the user picks — this is the correction. */
  as_table?: boolean
}

export interface QuestionMessagePayload {
  session_id: string
  chapters: {
    section_id: string
    title: string
    questions: UserQuestion[]
  }[]
}

export interface ProgressMessagePayload {
  session_id: string
  status: string
  current_step?: string | null
  chapters: ProgressChapter[]
}

export interface ReportMessagePayload {
  session_id: string
  artifacts: ReportArtifact[]
}

/** One turn in a conversation. `kind` selects the renderer; `payload` feeds it. */
export interface Message {
  message_id: string
  conversation_id: string
  role: MessageRole
  kind: MessageKind
  content: string
  payload: Record<string, unknown>
  attachments: MessageAttachment[]
  created_at: string
}

export interface Conversation {
  conversation_id: string
  user_id: string
  title: string
  report_session_id?: string | null
  created_at: string
  updated_at: string
}

export interface ConversationDetail {
  conversation: Conversation
  messages: Message[]
  report_session?: ReportGenerationSession | null
}
