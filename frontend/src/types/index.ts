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
  ReportGlobalContext,
  ChapterPlan,
  SubchapterPlan,
  DataSourceMetadata,
  UserQuestion,
  ChapterDraft,
  MetricFinding,
  SqlRead,
  ReportFact,
  AssembledReport,
  ReportArtifact,
  ReportGenerationSession,
} from './report'

export type {
  MessageRole,
  MessageKind,
  AttachmentKind,
  MessageAttachment,
  PlanMessagePayload,
  ProgressChapter,
  ChapterProgressStatus,
  QuestionResolutionInput,
  QuestionMessagePayload,
  ProgressMessagePayload,
  ReportMessagePayload,
  Message,
  Conversation,
  ConversationDetail,
} from './conversation'

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

export type {
  ConnectionDriver,
  ConnectionStatus,
  DriverExtraField,
  DriverSpec,
  DataConnection,
  ConnectionInput,
  ConnectionTestResult,
  ConnectionQueryResult,
  MetricExtraction,
  SupplementShape,
  AnalysisType,
  AnalysisSqlResult,
  ParsedTable,
} from './connection'
