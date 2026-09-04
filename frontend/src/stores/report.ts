import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  ReportTemplate,
  ReportGenerationSession,
  CreateReportGenerationRequest,
  AnswerReportQuestionRequest,
} from '../types'
import { reportApi } from '../services/api/reports'

const POLL_INTERVAL_MS = 2000

export const useReportStore = defineStore('report', () => {
  const templates = ref<ReportTemplate[]>([])
  const currentSession = ref<ReportGenerationSession | null>(null)
  const loadingTemplate = ref(false)
  const loadingSession = ref(false)
  const loadingTemplates = ref(false)
  const loadingSessions = ref(false)
  const totalTemplates = ref(0)
  const templatesHasMore = ref(false)
  const sessions = ref<ReportGenerationSession[]>([])
  const totalSessions = ref(0)
  const sessionsHasMore = ref(false)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function startPolling(sessionId: string) {
    stopPolling()
    pollTimer = setInterval(async () => {
      const res = await reportApi.getSession(sessionId)
      if (res.success && res.data) {
        currentSession.value = res.data
        const st = res.data.status
        if (st === 'completed' || st === 'failed' || st === 'cancelled') {
          stopPolling()
        }
      } else if (res.error?.code === 'REQUEST_FAILED' && (
        /404/.test(res.error.message) ||
        /not found|不存在|未找到|session.*not/i.test(res.error.message)
      )) {
        // 后端使用内存 session 时，重启会使旧 session 失效；停止轮询，避免持续刷 404。
        stopPolling()
        error.value = '报告任务已失效，请重新提交生成'
      }
    }, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function loadTemplates(offset = 0, limit = 50, replace = true) {
    loadingTemplates.value = true
    error.value = null
    try {
      const res = await reportApi.listTemplates(offset, limit)
      if (res.success && res.data) {
        const list = Array.isArray(res.data.items) ? res.data.items : []
        templates.value = replace ? list : [...templates.value, ...list]
        totalTemplates.value = Number(res.data.total) || templates.value.length
        templatesHasMore.value = Boolean(res.data.has_more)
        return templates.value
      }
      if (res.error) {
        error.value = res.error.message
      }
      return replace ? [] : templates.value
    } catch (e) {
      error.value = String(e)
      return replace ? [] : templates.value
    } finally {
      loadingTemplates.value = false
    }
  }

  async function loadSessions(offset = 0, limit = 20, replace = true) {
    loadingSessions.value = true
    error.value = null
    try {
      const res = await reportApi.listSessions(offset, limit)
      if (res.success && res.data) {
        const list = Array.isArray(res.data.items) ? res.data.items : []
        sessions.value = replace ? list : [...sessions.value, ...list]
        totalSessions.value = Number(res.data.total) || sessions.value.length
        sessionsHasMore.value = Boolean(res.data.has_more)
        return sessions.value
      }
      if (res.error) {
        error.value = res.error.message
      }
      return replace ? [] : sessions.value
    } catch (e) {
      error.value = String(e)
      return replace ? [] : sessions.value
    } finally {
      loadingSessions.value = false
    }
  }

  async function uploadTemplate(file: File) {
    loadingTemplate.value = true
    error.value = null
    try {
      const res = await reportApi.uploadTemplate(file)
      if (res.success && res.data) {
        templates.value.unshift(res.data)
        return res.data
      }
      if (res.error) error.value = res.error.message
      return null
    } catch (e) {
      error.value = String(e)
      return null
    } finally {
      loadingTemplate.value = false
    }
  }

  async function createSession(request: CreateReportGenerationRequest) {
    loadingSession.value = true
    error.value = null
    currentSession.value = null
    try {
      const res = await reportApi.createSession(request)
      if (res.success && res.data) {
        currentSession.value = res.data
        if (request.auto_start && (res.data.status === 'created' || res.data.status === 'running')) {
          startPolling(res.data.session_id)
        }
        return res.data
      }
      if (res.error) error.value = res.error.message
      return null
    } catch (e) {
      error.value = String(e)
      return null
    } finally {
      loadingSession.value = false
    }
  }

  async function reloadSession(sessionId: string) {
    loadingSession.value = true
    error.value = null
    try {
      const res = await reportApi.getSession(sessionId)
      if (res.success && res.data) {
        currentSession.value = res.data
        const st = res.data.status
        if (st === 'created' || st === 'running' || st === 'waiting_user') {
          startPolling(sessionId)
        }
      } else if (res.error) {
        error.value = res.error.message
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loadingSession.value = false
    }
  }

  async function answerQuestion(sessionId: string, request: AnswerReportQuestionRequest) {
    loadingSession.value = true
    error.value = null
    try {
      const res = await reportApi.answerQuestion(sessionId, request)
      if (res.success && res.data) {
        currentSession.value = res.data
        if (request.auto_resume) {
          startPolling(sessionId)
        }
      } else if (res.error) {
        error.value = res.error.message
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loadingSession.value = false
    }
  }

  async function resumeSession(sessionId: string) {
    loadingSession.value = true
    error.value = null
    try {
      const res = await reportApi.resumeSession(sessionId)
      if (res.success && res.data) {
        currentSession.value = res.data
        startPolling(sessionId)
      } else if (res.error) {
        error.value = res.error.message
      }
    } catch (e) {
      error.value = String(e)
    } finally {
      loadingSession.value = false
    }
  }

  function addTemplate(tpl: ReportTemplate) {
    templates.value.unshift(tpl)
  }

  function clearError() {
    error.value = null
  }

  function $reset() {
    stopPolling()
    templates.value = []
    sessions.value = []
    totalTemplates.value = 0
    totalSessions.value = 0
    templatesHasMore.value = false
    sessionsHasMore.value = false
    currentSession.value = null
    loadingTemplate.value = false
    loadingSession.value = false
    loadingTemplates.value = false
    loadingSessions.value = false
    error.value = null
  }

  return {
    templates,
    sessions,
    totalTemplates,
    totalSessions,
    templatesHasMore,
    sessionsHasMore,
    currentSession,
    loadingTemplate,
    loadingTemplates,
    loadingSession,
    loadingSessions,
    error,
    startPolling,
    stopPolling,
    loadTemplates,
    loadSessions,
    uploadTemplate,
    createSession,
    reloadSession,
    answerQuestion,
    resumeSession,
    addTemplate,
    clearError,
    $reset,
  }
})
