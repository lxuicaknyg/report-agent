<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { TaskEvent } from '../../types'
import { useConversationStore } from '../../stores/conversation'
import { useTaskStore } from '../../stores/task'
import { sseClient } from '../../services/events'
import ChatPanel from './ChatPanel.vue'

const route = useRoute()
const conversationStore = useConversationStore()
const taskStore = useTaskStore()

const sessionId = computed(() => route.params.sessionId as string)
const currentTask = computed(() => conversationStore.currentTask)
const currentPlan = computed(() => conversationStore.currentPlan)
const allTasks = computed(() => conversationStore.tasks)

let unsubscribeSSE: (() => void) | null = null

onMounted(async () => {
  await conversationStore.ensureSessionListLoaded()

  if (sessionId.value) {
    try {
      await conversationStore.selectSession(sessionId.value)
    } catch {
      if (conversationStore.sessions.length === 0) {
        await conversationStore.createSession('新会话')
      }
    }
  } else if (conversationStore.sessions.length > 0) {
    await conversationStore.selectSession(conversationStore.sessions[0].id)
  } else {
    await conversationStore.createSession('新会话')
  }

  unsubscribeSSE = sseClient.on('*', (event: TaskEvent) => {
    handleSSEEvent(event)
  })

  if (currentTask.value?.id) {
    sseClient.connect(currentTask.value.id)
  }
})

onUnmounted(() => {
  if (unsubscribeSSE) {
    unsubscribeSSE()
  }
  sseClient.disconnect()
})

watch(sessionId, async (newId, oldId) => {
  if (newId && newId !== oldId) {
    sseClient.disconnect()
    if (unsubscribeSSE) {
      unsubscribeSSE()
    }

    try {
      await conversationStore.selectSession(newId)
    } catch {
      if (conversationStore.sessions.length > 0) {
        await conversationStore.selectSession(conversationStore.sessions[0].id)
      }
    }

    unsubscribeSSE = sseClient.on('*', (event: TaskEvent) => {
      handleSSEEvent(event)
    })
  }
})

watch(() => currentTask.value?.id, (newId, oldId) => {
  if (newId && newId !== oldId) {
    sseClient.connect(newId)
  }
})

function handleSSEEvent(event: TaskEvent) {
  const task = conversationStore.tasks.find((t) => t.id === event.task_id)
  if (!task) return

  const updated = taskStore.applyEvent(task, event)
  conversationStore.setTask(updated)

  if (event.event === 'task.completed' || event.event === 'task.failed' || event.event === 'task.cancelled') {
    sseClient.disconnect()
    void conversationStore.refreshTask(event.task_id)

    if (event.event === 'task.completed') {
      const sessionTasks = conversationStore.getSessionTasks(task.conversation_id).filter(
        (t) => t.id !== task.id || t.status === 'completed',
      )
      if (sessionTasks.length <= 1) {
        const session = conversationStore.sessions.find((s) => s.id === task.conversation_id)
        if (session?.title === '新会话' || session?.title === '新对话') {
          conversationStore.updateConversationTitle(session.id, task.prompt)
        }
      }
    }
  }
}
</script>

<template>
  <div class="conversation-view">
    <ChatPanel
      :plan="currentPlan"
      :task="currentTask"
      :tasks="allTasks"
    />
  </div>
</template>

<style scoped>
.conversation-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>
