import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { Conversation, Message, ReportGenerationSession } from '../types'
import { conversationApi, type PostMessageInput } from '../services/api/conversations'

const POLL_INTERVAL_MS = 2000

/**
 * Server-backed conversation state.
 *
 * The backend owns every transition; this store only mirrors it. There is no
 * local cache to reconcile, and no business branching here — messages arrive
 * already shaped for rendering.
 */
export const useConversationStore = defineStore('conversation', () => {
  const conversations = ref<Conversation[]>([])
  const messages = ref<Message[]>([])
  const currentConversationId = ref<string | null>(null)
  const reportSession = ref<ReportGenerationSession | null>(null)
  const isLoading = ref(false)
  const isSending = ref(false)
  const isCancelling = ref(false)
  const error = ref<string | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const currentConversation = computed(
    () => conversations.value.find((item) => item.conversation_id === currentConversationId.value) ?? null,
  )

  /** True while the backend still owes us an assistant turn. */
  const isAwaitingAssistant = computed(() => {
    const last = messages.value[messages.value.length - 1]
    if (!last) return false
    if (last.role === 'user') return true
    const status = reportSession.value?.status
    return status === 'created' || status === 'running'
  })

  /** True while a run is in flight and can be stopped. */
  const isGenerating = computed(() => {
    const status = reportSession.value?.status
    return status === 'created' || status === 'running'
  })

  /** True for a run that stopped with progress on disk and can be picked up again. */
  const isResumable = computed(() => {
    const status = reportSession.value?.status
    return status === 'cancelled' || status === 'failed'
  })

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(async () => {
      if (!currentConversationId.value) return stopPolling()
      await refresh(currentConversationId.value)
      if (!isAwaitingAssistant.value) stopPolling()
    }, POLL_INTERVAL_MS)
  }

  async function loadConversations() {
    isLoading.value = true
    try {
      const result = await conversationApi.list()
      if (result.success && Array.isArray(result.data)) conversations.value = result.data
      else if (result.error) error.value = result.error.message
      return conversations.value
    } finally {
      isLoading.value = false
    }
  }

  async function refresh(conversationId: string) {
    const result = await conversationApi.get(conversationId)
    if (!result.success || !result.data) {
      if (result.error) error.value = result.error.message
      return null
    }
    if (currentConversationId.value !== conversationId) return result.data
    messages.value = result.data.messages
    reportSession.value = result.data.report_session ?? null
    const index = conversations.value.findIndex((item) => item.conversation_id === conversationId)
    if (index === -1) conversations.value.unshift(result.data.conversation)
    else conversations.value[index] = result.data.conversation
    return result.data
  }

  async function selectConversation(conversationId: string) {
    stopPolling()
    currentConversationId.value = conversationId
    messages.value = []
    reportSession.value = null
    isLoading.value = true
    try {
      await refresh(conversationId)
      if (isAwaitingAssistant.value) startPolling()
    } finally {
      isLoading.value = false
    }
  }

  async function createConversation(title?: string): Promise<Conversation | null> {
    const result = await conversationApi.create(title)
    if (!result.success || !result.data) {
      if (result.error) error.value = result.error.message
      return null
    }
    conversations.value.unshift(result.data)
    currentConversationId.value = result.data.conversation_id
    messages.value = []
    reportSession.value = null
    return result.data
  }

  async function sendMessage(input: PostMessageInput): Promise<boolean> {
    const conversationId = currentConversationId.value
    if (!conversationId) {
      error.value = '当前会话尚未准备完成，请稍后重试'
      return false
    }
    isSending.value = true
    error.value = null
    try {
      const result = await conversationApi.postMessage(conversationId, input)
      if (!result.success || !result.data) {
        error.value = result.error?.message || '消息发送失败，请重试'
        return false
      }
      messages.value = [...messages.value, result.data]
      startPolling()
      return true
    } finally {
      isSending.value = false
    }
  }

  async function cancelGeneration(): Promise<boolean> {
    const conversationId = currentConversationId.value
    if (!conversationId || isCancelling.value) return false
    isCancelling.value = true
    error.value = null
    try {
      const result = await conversationApi.cancel(conversationId)
      if (!result.success) {
        error.value = result.error?.message || '停止失败，请重试'
        return false
      }
      // The stop posts its own message, so pull the thread rather than
      // patching state locally and drifting from what the backend recorded.
      await refresh(conversationId)
      stopPolling()
      return true
    } finally {
      isCancelling.value = false
    }
  }

  async function deleteConversation(conversationId: string) {
    conversations.value = conversations.value.filter((item) => item.conversation_id !== conversationId)
    if (currentConversationId.value === conversationId) {
      stopPolling()
      currentConversationId.value = null
      messages.value = []
      reportSession.value = null
    }
    await conversationApi.remove(conversationId)
  }

  function clearError() {
    error.value = null
  }

  return {
    conversations,
    messages,
    currentConversationId,
    currentConversation,
    reportSession,
    isLoading,
    isSending,
    isCancelling,
    isGenerating,
    isResumable,
    isAwaitingAssistant,
    error,
    loadConversations,
    refresh,
    selectConversation,
    createConversation,
    sendMessage,
    cancelGeneration,
    deleteConversation,
    clearError,
    stopPolling,
  }
})
