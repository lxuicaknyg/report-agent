import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Task, TaskEvent, TaskStep, ExecutionPlan } from '../types'
import { taskApi } from '../services/api'

export const useTaskStore = defineStore('task', () => {
  const isLoading = ref(false)

  async function fetchTask(taskId: string): Promise<Task | null> {
    isLoading.value = true
    try {
      const result = await taskApi.getTask(taskId)
      if (result.success && result.data) {
        return result.data
      }
      return null
    } finally {
      isLoading.value = false
    }
  }

  function applyEvent(task: Task, event: TaskEvent): Task {
    const updates: Partial<Task> = {}

    if (event.status) {
      updates.status = event.status as Task['status']
    }

    if (event.event === 'plan.generated' && event.data) {
      const planData = event.data as {
        plan_id?: string
        summary?: string
        version?: number
        steps?: Array<{
          id: string; title: string; tool_name?: string | null; agent_name?: string | null;
          kind?: 'agent' | 'tool'; depends_on?: string[]; section_id?: string | null
        }>
      }
      const steps = (planData.steps ?? []).map((s): TaskStep => ({
        id: s.id,
        title: s.title,
        tool_name: typeof s.tool_name === 'string' ? s.tool_name : null,
        agent_name: typeof s.agent_name === 'string' ? s.agent_name : null,
        kind: s.kind ?? 'agent',
        status: 'pending',
        depends_on: Array.isArray(s.depends_on) ? s.depends_on : [],
        section_id: typeof s.section_id === 'string' ? s.section_id : null,
        error: null,
        attempt: 0,
        started_at: null,
        completed_at: null,
        result: null,
      }))
      const plan: ExecutionPlan = {
        id: typeof planData.plan_id === 'string' ? planData.plan_id : `plan_${task.id}`,
        task_id: task.id,
        summary: typeof planData.summary === 'string' ? planData.summary : '',
        status: 'generated',
        version: typeof planData.version === 'number' ? planData.version : 1,
        steps,
        created_at: task.created_at,
        updated_at: new Date().toISOString(),
        completed_at: null,
        error: null,
      }
      updates.plan = plan
    }

    if (event.event === 'step.started' && event.step_id) {
      const plan = task.plan
      if (plan) {
        const stepIdx = plan.steps.findIndex((s) => s.id === event.step_id)
        if (stepIdx !== -1) {
          plan.steps[stepIdx] = {
            ...plan.steps[stepIdx],
            status: 'running',
            started_at: event.timestamp ?? new Date().toISOString(),
          }
          updates.plan = { ...plan, updated_at: new Date().toISOString() }
        }
      }
    }

    if (event.event === 'step.completed' && event.step_id) {
      const plan = task.plan
      if (plan) {
        const stepIdx = plan.steps.findIndex((s) => s.id === event.step_id)
        if (stepIdx !== -1) {
          const evData = (event.data ?? {}) as { result?: TaskStep['result'] }
          plan.steps[stepIdx] = {
            ...plan.steps[stepIdx],
            status: 'completed',
            completed_at: event.timestamp ?? new Date().toISOString(),
            result: evData.result ?? plan.steps[stepIdx].result,
          }
          updates.plan = { ...plan, updated_at: new Date().toISOString() }

          if (evData.result && typeof evData.result === 'object') {
            const r = evData.result as Record<string, unknown>
            if (typeof r.body_markdown === 'string' && !updates.result) {
              updates.result = {
                summary: r.body_markdown as string,
                cited_metrics: Array.isArray(r.cited_metrics) ? (r.cited_metrics as string[]) : [],
                cited_sections: Array.isArray(r.cited_sections) ? (r.cited_sections as string[]) : [],
                followup_suggestions: Array.isArray(r.followup_suggestions) ? (r.followup_suggestions as string[]) : [],
                sub_type: typeof r.sub_type === 'string' ? r.sub_type : '',
              } as Task['result']
            }
          }
        }
      }
    }

    if (event.event === 'step.failed' && event.step_id) {
      const plan = task.plan
      if (plan) {
        const stepIdx = plan.steps.findIndex((s) => s.id === event.step_id)
        if (stepIdx !== -1) {
          const errData = event.data as { error?: string }
          plan.steps[stepIdx] = {
            ...plan.steps[stepIdx],
            status: 'failed',
            error: typeof errData?.error === 'string' ? errData.error : null,
            completed_at: event.timestamp ?? new Date().toISOString(),
          }
          updates.plan = { ...plan, updated_at: new Date().toISOString() }
        }
      }
      const errData = event.data as { error?: string }
      if (errData?.error && !updates.error) {
        updates.error = errData.error
      }
    }

    if (event.event === 'tool.started' && event.step_id) {
      const plan = task.plan
      if (plan) {
        const stepIdx = plan.steps.findIndex((s) => s.id === event.step_id)
        if (stepIdx !== -1) {
          plan.steps[stepIdx] = {
            ...plan.steps[stepIdx],
            status: 'running',
            started_at: event.timestamp ?? new Date().toISOString(),
          }
          updates.plan = { ...plan, updated_at: new Date().toISOString() }
        }
      }
    }

    if (event.event === 'tool.completed' && event.step_id) {
      const plan = task.plan
      if (plan) {
        const stepIdx = plan.steps.findIndex((s) => s.id === event.step_id)
        if (stepIdx !== -1) {
          plan.steps[stepIdx] = {
            ...plan.steps[stepIdx],
            status: 'completed',
            completed_at: event.timestamp ?? new Date().toISOString(),
          }
          updates.plan = { ...plan, updated_at: new Date().toISOString() }
        }
      }
    }

    if (event.event === 'tool.failed' && event.step_id) {
      const plan = task.plan
      if (plan) {
        const stepIdx = plan.steps.findIndex((s) => s.id === event.step_id)
        if (stepIdx !== -1) {
          const errData = event.data as { error?: string }
          plan.steps[stepIdx] = {
            ...plan.steps[stepIdx],
            status: 'failed',
            error: typeof errData?.error === 'string' ? errData.error : null,
            completed_at: event.timestamp ?? new Date().toISOString(),
          }
          updates.plan = { ...plan, updated_at: new Date().toISOString() }
        }
      }
      const errData = event.data as { error?: string }
      if (errData?.error) {
        updates.error = errData.error
      }
    }

    if (event.event === 'task.failed' && event.data) {
      const errData = event.data as { error?: string }
      if (errData?.error) {
        updates.error = errData.error
      }
    }

    if (event.event === 'task.cancelled' && event.data) {
      const errData = event.data as { error?: string }
      if (errData?.error) {
        updates.error = errData.error
      }
    }

    if (event.event === 'result.available' && event.data) {
      updates.result = event.data
    }

    return { ...task, ...updates }
  }

  return {
    isLoading,
    fetchTask,
    applyEvent,
  }
})
