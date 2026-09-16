<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useConversationStore } from '../../stores/conversation'
import ChatPanel from './ChatPanel.vue'

const route = useRoute()
const router = useRouter()
const store = useConversationStore()

const conversationId = computed(() => String(route.params.conversationId || ''))

/** The route owns the selection; /conversations/new creates one on arrival. */
async function sync(id: string) {
  if (id) {
    await store.selectConversation(id)
    return
  }
  const created = await store.createConversation()
  if (created) {
    await router.replace({
      name: 'conversation-detail',
      params: { conversationId: created.conversation_id },
    })
  }
}

onMounted(async () => {
  await store.loadConversations()
  await sync(conversationId.value)
})

watch(conversationId, (id, previous) => {
  if (id !== previous) void sync(id)
})

onUnmounted(() => store.stopPolling())
</script>

<template>
  <div class="conversation-view">
    <ChatPanel />
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
