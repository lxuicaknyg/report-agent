import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ConversationSession, Task } from '../types'
import { conversationApi, type SubmitTaskAttachmentRef } from '../services/api'
import { taskApi } from '../services/api'

const LS_SESSIONS_KEY = 'report-agent:sessions-v1'
const LS_TASKS_KEY = 'report-agent:conversation-tasks-v1'

function loadSessionsFromLS(): ConversationSession[] {
  try {
    const raw = localStorage.getItem(LS_SESSIONS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x): x is ConversationSession =>
      x && typeof x === 'object' &&
      typeof (x as Record<string, unknown>).id === 'string' &&
      typeof (x as Record<string, unknown>).title === 'string'
    )
  } catch {
    return []
  }
}

function persistSessions(sessions: ConversationSession[]) {
  try {
    localStorage.setItem(LS_SESSIONS_KEY, JSON.stringify(sessions.map(s => ({
      id: s.id,
      title: s.title,
      created_at: s.created_at,
      updated_at: s.updated_at,
    }))))
  } catch {
    /* ignore */
  }
}

function loadTasksFromLS(): Task[] {
  try {
    const raw = localStorage.getItem(LS_TASKS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x): x is Task =>
      x && typeof x === 'object' &&
      typeof (x as Record<string, unknown>).id === 'string' &&
      typeof (x as Record<string, unknown>).conversation_id === 'string'
    )
  } catch {
    return []
  }
}

function persistTasks(tasks: Task[]) {
  try {
    localStorage.setItem(LS_TASKS_KEY, JSON.stringify(tasks))
  } catch {
    /* ignore */
  }
}

function createLocalSessionRecord(title?: string): ConversationSession {
  const now = new Date().toISOString()
  return {
    id: `local_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
    title: title?.trim() || '新会话',
    created_at: now,
    updated_at: now,
  }
}

function isConversationEndpointUnavailable(result: { success: boolean; error?: { code?: string; message?: string } }): boolean {
  if (result.success) return false
  const message = result.error?.message || ''
  const code = result.error?.code || ''
  return code === 'NOT_FOUND' || /404|not found|不存在|未找到/i.test(message)
}

export const useConversationStore = defineStore('conversation', () => {
  const sessions = ref<ConversationSession[]>(loadSessionsFromLS())
  const currentSessionId = ref<string | null>(null)
  const currentTaskId = ref<string | null>(null)
  const tasks = ref<Task[]>(loadTasksFromLS())
  const isLoading = ref(false)
  const isSending = ref(false)

  const currentSession = computed(() =>
    sessions.value.find((s) => s.id === currentSessionId.value) ?? null
  )

  const currentTask = computed(() =>
    tasks.value.find((t) => t.id === currentTaskId.value) ?? null
  )

  const currentPlan = computed(() => currentTask.value?.plan ?? null)

  const allTasks = computed(() => tasks.value)

  function getSessionTasks(sessionId: string): Task[] {
    return tasks.value.filter((t) => t.conversation_id === sessionId)
  }

  function getTaskCountByStatus(status: string): number {
    return tasks.value.filter((t) => t.status === status).length
  }

  async function createSession(title?: string): Promise<ConversationSession | null> {
    isLoading.value = true
    try {
      const result = await conversationApi.createSession(title)
      if (result.success && result.data) {
        sessions.value.unshift(result.data)
        persistSessions(sessions.value)
        currentSessionId.value = result.data.id
        currentTaskId.value = null
        return result.data
      }
      // 当前后端尚未提供 conversations CRUD；报告任务的会话关系可以先由前端本地维护。
      if (isConversationEndpointUnavailable(result)) {
        const localSession = createLocalSessionRecord(title)
        sessions.value.unshift(localSession)
        persistSessions(sessions.value)
        currentSessionId.value = localSession.id
        currentTaskId.value = null
        return localSession
      }
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function ensureSessionListLoaded() {
    try {
      isLoading.value = true
      const result = await conversationApi.listConversations()
      if (result.success && Array.isArray(result.data) && result.data.length > 0) {
        sessions.value = result.data.map(serverSession => {
          const idx = sessions.value.findIndex((s) => s.id === serverSession.id)
          if (idx === -1) return serverSession
          const existing = sessions.value[idx]
          const finalTitle =
            existing.title &&
            existing.title !== '新会话' &&
            existing.title !== '新对话'
              ? existing.title
              : (serverSession.title || existing.title || '新会话')
          return {
            ...serverSession,
            id: existing.id,
            title: finalTitle,
            created_at: existing.created_at || serverSession.created_at,
            updated_at: serverSession.updated_at || existing.updated_at,
          }
        })
        persistSessions(sessions.value)
      }
    } catch {
      /* 老版本后端没有 list 接口 — 保留 localStorage 中的 */
    } finally {
      isLoading.value = false
    }
  }

  async function selectSession(sessionId: string) {
    currentSessionId.value = sessionId
    isLoading.value = true
    try {
      // 本地兜底会话没有对应的后端资源，直接使用本地缓存即可。
      if (sessionId.startsWith('local_')) return
      const result = await conversationApi.getSession(sessionId)
      if (result.success && result.data) {
        const serverSession = result.data
        const idx = sessions.value.findIndex((s) => s.id === sessionId)
        if (idx !== -1) {
          const existing = sessions.value[idx]
          const finalTitle =
            existing.title &&
            existing.title !== '新会话' &&
            existing.title !== '新对话'
              ? existing.title
              : (serverSession.title || existing.title || '新会话')
          sessions.value[idx] = {
            ...serverSession,
            id: existing.id,
            title: finalTitle,
            created_at: existing.created_at || serverSession.created_at,
            updated_at: serverSession.updated_at || existing.updated_at,
          }
        } else {
          sessions.value.unshift(serverSession)
        }
        persistSessions(sessions.value)
      }
    } finally {
      isLoading.value = false
      const sessionTasks = tasks.value
        .filter((t) => t.conversation_id === sessionId)
        .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''))
      currentTaskId.value = sessionTasks.length > 0 ? sessionTasks[sessionTasks.length - 1].id : null
    }
  }

  async function sendMessage(
    content: string,
    opts?: { attachments?: SubmitTaskAttachmentRef[] },
  ): Promise<Task | null> {
    if (!currentSessionId.value) return null
    isSending.value = true
    try {
      const result = await conversationApi.submitTask(
        currentSessionId.value,
        content,
        { attachments: opts?.attachments },
      )
      if (result.success && result.data) {
        const task = result.data
        tasks.value.push(task)
        persistTasks(tasks.value)
        currentTaskId.value = task.id
        return task
      }
      return null
    } finally {
      isSending.value = false
    }
  }

  function setTask(task: Task) {
    const idx = tasks.value.findIndex((t) => t.id === task.id)
    if (idx !== -1) {
      tasks.value[idx] = task
    } else {
      tasks.value.push(task)
    }
    persistTasks(tasks.value)
    currentTaskId.value = task.id
  }

  function updateTask(taskId: string, updates: Partial<Task>) {
    const idx = tasks.value.findIndex((t) => t.id === taskId)
    if (idx !== -1) {
      tasks.value[idx] = { ...tasks.value[idx], ...updates }
      persistTasks(tasks.value)
    }
  }

  function clearCurrentTask() {
    currentTaskId.value = null
  }

  async function refreshTask(taskId: string): Promise<Task | null> {
    try {
      const result = await taskApi.getTask(taskId)
      if (result.success && result.data) {
        setTask(result.data)
        return result.data
      }
    } catch {
      /* ignore transient network errors — keep latest store value */
    }
    return null
  }

  function updateConversationTitle(sessionId: string, title: string) {
    if (!sessionId || !title) return
    const idx = sessions.value.findIndex((s) => s.id === sessionId)
    if (idx === -1) return
    const trimmed = title.trim()
    if (!trimmed) return
    const finalTitle = trimmed.length > 20 ? trimmed.slice(0, 20) + '…' : trimmed
    if (sessions.value[idx].title === finalTitle) return
    sessions.value[idx] = {
      ...sessions.value[idx],
      title: finalTitle,
      updated_at: new Date().toISOString(),
    }
    persistSessions(sessions.value)
  }

  async function deleteSession(sessionId: string) {
    const idx = sessions.value.findIndex((s) => s.id === sessionId)
    if (idx !== -1) {
      sessions.value.splice(idx, 1)
      persistSessions(sessions.value)
    }
    const taskCountBefore = tasks.value.length
    tasks.value = tasks.value.filter(t => t.conversation_id !== sessionId)
    if (tasks.value.length !== taskCountBefore) persistTasks(tasks.value)
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = null
      currentTaskId.value = null
    }
    try {
      await conversationApi.deleteSession(sessionId)
    } catch {
      /* 后端暂时无 DELETE 路由，静默本地删除即可 */
    }
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    currentTaskId,
    currentTask,
    currentPlan,
    tasks,
    allTasks,
    isLoading,
    isSending,
    createSession,
    selectSession,
    sendMessage,
    setTask,
    updateTask,
    clearCurrentTask,
    refreshTask,
    updateConversationTitle,
    deleteSession,
    getSessionTasks,
    getTaskCountByStatus,
    ensureSessionListLoaded,
  }
})
