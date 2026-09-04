import type { Evidence } from './analysis'

export type ReportGenerationStatus =
  | 'created'
  | 'awaiting_confirmation'
  | 'running'
  | 'waiting_user'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface ReportTemplateSection {
  section_id: string
  title: string
  level?: number
  order: number
  instructions?: string | null
  example_content?: string | null
  required_data?: string[]
  metadata?: Record<string, unknown>
}

export interface ReportTemplate {
  template_id: string
  filename: string
  title: string
  content_type?: string | null
  sections?: ReportTemplateSection[]
  assembly_rules?: Record<string, unknown>
  metadata?: Record<string, unknown>
  created_at: string
}

export interface ReportPlan {
  plan_id: string
  version: number
  status: 'generated' | 'awaiting_confirmation' | 'approved' | 'executing' | 'completed'
  template_id: string
  title: string
  instruction: string
  global_context: ReportGlobalContext
  chapters?: ChapterPlan[]
  sections?: ChapterPlan[]
  assembly_order?: string[]
  created_at: string
}

export interface ReportGlobalContext {
  report_period?: string | null
  dimensions: Record<string, string>
}

export interface ChapterPlan {
  section_id: string
  title: string
  metrics: string[]
  order?: number
}


export interface DataSourceMetadata {
  dataset_id: string
  name: string
  source_type: string
  description?: string | null
  sheets?: Record<string, unknown>[]
  columns?: Record<string, unknown>[]
  sample_rows?: Record<string, unknown>[]
  metadata?: Record<string, unknown>
}

export interface UserQuestion {
  question_id: string
  chapter_id?: string | null
  content: string
  reason?: string | null
  required?: boolean
  answer?: string | null
  created_at: string
  answered_at?: string | null
}

export interface ChapterDraft {
  chapter_id: string
  section_id: string
  title: string
  content?: string
  tables?: Record<string, unknown>[]
  charts?: Record<string, unknown>[]
  evidence?: Evidence[]
  assumptions?: string[]
  questions?: UserQuestion[]
  completed?: boolean
}

export interface AssembledReport {
  title: string
  executive_summary?: string
  chapters?: ChapterDraft[]
  evidence?: Evidence[]
  metadata?: Record<string, unknown>
}

export interface ReportArtifact {
  artifact_id: string
  name: string
  content_type: string
  uri: string
  format: string
  created_at: string
}

export interface ReportGenerationSession {
  session_id: string
  user_id: string
  template_id: string
  dataset_ids: string[]
  instruction: string
  title?: string | null
  status: ReportGenerationStatus
  current_step?: string | null
  current_chapter_id?: string | null
  template_snapshot?: ReportTemplate | null
  plan?: ReportPlan | null
  chapter_drafts?: Record<string, ChapterDraft>
  pending_questions?: UserQuestion[]
  answers?: Record<string, string>
  assembled_report?: AssembledReport | null
  artifacts?: ReportArtifact[]
  error?: string | null
  created_at: string
  updated_at: string
}

export interface CreateReportGenerationRequest {
  template_id: string
  dataset_ids: string[]
  instruction: string
  title?: string | null
  auto_start?: boolean
}

export interface AnswerReportQuestionRequest {
  question_id: string
  answer: string
  auto_resume?: boolean
}

export interface ConfirmReportPlanRequest {
  title?: string | null
  report_period?: string | null
  dimensions?: Record<string, string>
  chapters?: Array<{
    section_id: string
    title: string
    metrics: string[]
  }>
}

export interface LegacyProfileReportResponse {
  report: {
    title: string
    executive_summary: string
    sections?: Record<string, unknown>[]
    evidence?: Evidence[]
    format?: 'markdown' | 'html'
  }
  markdown: string
}
