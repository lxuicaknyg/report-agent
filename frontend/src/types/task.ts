export type TaskStatus =
  | 'created'
  | 'planning'
  | 'running'
  | 'needs_data'
  | 'waiting_user'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type StepStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'needs_data'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'cancelled'

export type PlanStatus = 'generated' | 'running' | 'needs_data' | 'completed' | 'failed' | 'cancelled'

export interface TaskStep {
  id: string
  title: string
  tool_name: string | null
  agent_name: string | null
  kind: 'agent' | 'tool'
  status: StepStatus
  depends_on: string[]
  section_id: string | null
  error: string | null
  attempt: number
  started_at: string | null
  completed_at: string | null
  result: Record<string, unknown> | null
}

export interface ExecutionPlan {
  id: string
  task_id: string
  summary: string
  status: PlanStatus
  version: number
  steps: TaskStep[]
  created_at: string
  updated_at: string
  completed_at: string | null
  error: string | null
}

import type { ReportGenerationSession } from './report'

export interface Task {
  id: string
  conversation_id: string
  turn_id: string
  prompt: string
  status: TaskStatus
  attachments: string[]
  plan: ExecutionPlan | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
  /** 报告工作流任务的前端关联状态 */
  report_session?: ReportGenerationSession | null
}

export type PlanResponse = ExecutionPlan
export type PlanStepResponse = TaskStep
export type TaskResult = Record<string, unknown>
export interface TaskReportResponse {
  task_id: string
  title?: string
  markdown?: string
  sections?: Array<Record<string, unknown>>
  statistics?: Record<string, unknown>
  evidence?: Array<Record<string, unknown>>
  format?: 'markdown' | 'html'
  created_at?: string
}
