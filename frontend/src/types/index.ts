export type {
  SourceType,
  User,
  ColumnSchema,
  SheetInfo,
  DataReadRequest,
  DataReadResult,
  DatasetInfo,
  DatasetProfile,
  SqlRegisterRequest,
} from './dataset'

export type {
  EvidenceKind,
  Evidence,
  AnalysisRequest,
  QueryResult,
  AnalysisResult,
  ProfileResult,
} from './analysis'

export type {
  ReportGenerationStatus,
  ReportTemplateSection,
  ReportTemplate,
  ReportPlan,
  DataSourceMetadata,
  UserQuestion,
  ChapterDraft,
  AssembledReport,
  ReportArtifact,
  ReportGenerationSession,
  CreateReportGenerationRequest,
  AnswerReportQuestionRequest,
  LegacyProfileReportResponse,
} from './report'

export type { ConversationSession, Turn } from './conversation'
export type {
  TaskStatus,
  StepStatus,
  PlanStatus,
  TaskStep,
  ExecutionPlan,
  Task,
  PlanResponse,
  PlanStepResponse,
  TaskResult,
  TaskReportResponse,
} from './task'
export { TASK_EVENT_NAMES } from './events'
export type { TaskEvent, TaskEventName, SSEConnectionState } from './events'

export interface ApiErrorInfo {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface ApiResult<T> {
  success: boolean
  data?: T | null
  error?: ApiErrorInfo
}
