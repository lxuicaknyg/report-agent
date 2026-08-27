export const TASK_EVENT_NAMES = [
  'task.created',
  'task.running',
  'intent.detected',
  'plan.generated',
  'plan.failed',
  'plan.updated',
  'approval.required',
  'tool.queued',
  'step.queued',
  'tool.started',
  'tool.progress',
  'tool.completed',
  'tool.failed',
  'result.available',
  'user.intervention',
  'report.section.updated',
  'task.needs_data',
  'task.paused',
  'task.completed',
  'task.failed',
  'task.cancelled',
  'supervisor.routed',
  'graph.supervisor.started',
  'graph.supervisor.completed',
  'graph.agent.started',
  'graph.agent.completed',
  'graph.agent.failed',
  'graph.tool.started',
  'graph.tool.completed',
  'graph.tool.failed',
  'step.started',
  'step.completed',
  'step.failed',
  'step.skipped',
  'agent.started',
  'agent.completed',
  'agent.failed',
  'agent.reasoning.started',
  'agent.reasoning.completed',
  'agent.reasoning.failed',
  'agent.tool_selected',
  'agent.tool.started',
  'agent.tool.completed',
  'agent.tool.failed',
] as const

export type TaskEventName = (typeof TASK_EVENT_NAMES)[number]

export interface TaskEvent {
  id: number
  event: TaskEventName
  task_id: string
  timestamp: string
  step_id: string | null
  tool_name: string | null
  agent_name: string | null
  source: 'runtime' | 'supervisor' | 'agent' | 'tool' | 'langgraph'
  tool_call_id: string | null
  parent_event_id: number | null
  status: string | null
  data: Record<string, unknown>
}

export interface SSEConnectionState {
  status: 'closed' | 'connecting' | 'connected' | 'disconnected' | 'reconnecting'
  last_reconnect_at: string | null
  reconnect_attempts: number
}
