<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore, useConversationStore } from '../stores'
import type { Conversation } from '../types'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const conversationStore = useConversationStore()

const SIDEBAR_STATE_KEY = 'report-agent:sidebar-open-v1'
const showSidebar = ref(true)

const userInitial = computed(() =>
  (authStore.username || 'A').slice(0, 1).toUpperCase(),
)

const sessions = computed(() => conversationStore.conversations)
const currentSessionId = computed(() => {
  const id = route.params.conversationId as string | undefined
  return id ?? conversationStore.currentConversationId
})

const sortedSessions = computed(() => {
  return [...sessions.value].sort((a, b) => {
    const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0
    const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0
    return tb - ta
  })
})

const isConversationRoute = computed(
  () =>
    route.name === 'conversations' ||
    route.name === 'conversation-new' ||
    route.name === 'conversation-detail',
)

const activeNav = computed(() => {
  if (isConversationRoute.value) return 'reports'
  return String(route.meta.nav || route.path.split('/')[1] || '')
})

onMounted(async () => {
  try {
    const saved = localStorage.getItem(SIDEBAR_STATE_KEY)
    if (saved === '0') showSidebar.value = false
  } catch {
    /* ignore */
  }
  try {
    await conversationStore.loadConversations()
  } catch {
    /* ignore — 后端暂无路由时 LS 兜底 */
  }
})

watch(showSidebar, (v) => {
  try {
    localStorage.setItem(SIDEBAR_STATE_KEY, v ? '1' : '0')
  } catch {
    /* ignore */
  }
})

async function handleLogout() {
  authStore.logout()
  await router.push('/login')
}

async function handleNewSession() {
  const s = await conversationStore.createConversation()
  if (s) {
    await router.push({
      name: 'conversation-detail',
      params: { conversationId: s.conversation_id },
    })
  } else {
    await router.push({ name: 'conversation-new' })
  }
}

function openSession(s: Conversation) {
  router.push({
    name: 'conversation-detail',
    params: { conversationId: s.conversation_id },
  })
}

function toggleSidebar() {
  showSidebar.value = !showSidebar.value
}

async function handleDeleteSession(
  sessionId: string,
  sessionTitle: string,
) {
  const ok = window.confirm(
    `确定删除会话「${sessionTitle || '新会话'}」吗？此操作不可撤销。`,
  )
  if (!ok) return
  const wasActive =
    currentSessionId.value === sessionId && isConversationRoute.value
  await conversationStore.deleteConversation(sessionId)
  if (wasActive) {
    await router.push({ name: 'conversation-new' })
  }
}

function formatTime(s: Conversation): string {
  if (!s.updated_at) return ''
  try {
    const d = new Date(s.updated_at)
    const today = new Date()
    const sameDay = d.toDateString() === today.toDateString()
    if (sameDay) {
      return `${String(d.getHours()).padStart(2, '0')}:${String(
        d.getMinutes(),
      ).padStart(2, '0')}`
    }
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch {
    return ''
  }
}
</script>

<template>
  <div class="workspace">
    <!-- 顶栏：严格对齐 ai-report-dev 3 项导航风格 -->
    <header class="top-bar">
      <div class="brand-area">
        <img src="/logo.png" alt="Logo" class="brand-logo" />
        <span class="brand-divider" aria-hidden="true"></span>
        <div class="brand-copy">
          <strong>AI数据分析工作台</strong>
          <span class="brand-copy-en">AI Analysis</span>
        </div>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <RouterLink
          :to="{ name: 'conversation-new' }"
          class="primary-nav-item"
          :class="{ active: activeNav === 'reports' }"
          >报告生成</RouterLink
        >
        <span
          class="primary-nav-item disabled"
          title="历史记录接口尚未开放"
          >报告记录</span
        >
        <span
          class="primary-nav-item disabled"
          title="能力目录暂未开放为独立页面"
          >能力目录</span
        >
      </nav>

      <div class="account-area">
        <span class="avatar" aria-hidden="true">{{ userInitial }}</span>
        <span class="account-name">{{ authStore.username || '管理员' }}</span>
        <button
          class="logout-button"
          type="button"
          @click="handleLogout"
        >退出</button>
      </div>
    </header>

    <div class="workspace-body">
      <!-- 侧栏：单态会话列表，严格截图 -->
      <aside
        class="sidebar"
        aria-label="会话侧边栏"
        :class="{ collapsed: !showSidebar }"
      >
        <div class="sidebar-inner">
          <div class="sidebar-section sidebar-top">
            <button
              type="button"
              class="new-session-btn"
              @click="handleNewSession"
            >
              <span>新会话</span>
            </button>
            <RouterLink
              :to="{ name: 'connections' }"
              class="sidebar-link"
              :class="{ active: activeNav === 'connections' }"
            >
              <span class="sidebar-link-icon" aria-hidden="true">
                <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
                  <ellipse cx="8" cy="3.6" rx="5.2" ry="2.1" />
                  <path d="M2.8 3.6v8.8c0 1.16 2.33 2.1 5.2 2.1s5.2-.94 5.2-2.1V3.6" />
                  <path d="M2.8 8c0 1.16 2.33 2.1 5.2 2.1s5.2-.94 5.2-2.1" />
                </svg>
              </span>
              <span>数据源</span>
            </RouterLink>
          </div>

          <div class="sidebar-section">
            <div class="section-label">最近</div>
            <div class="session-list">
              <div v-if="sortedSessions.length === 0" class="session-empty">
                暂无会话
              </div>
              <div
                v-for="s in sortedSessions"
                :key="s.conversation_id"
                class="session-item-wrap"
              >
                <button
                  type="button"
                  class="session-item"
                  :class="{
                    active: currentSessionId === s.conversation_id && isConversationRoute,
                  }"
                  @click="openSession(s)"
                  :title="s.title"
                >
                  <span class="session-title">{{ s.title }}</span>
                  <span class="session-time">{{ formatTime(s) }}</span>
                </button>
                <button
                  type="button"
                  class="session-delete"
                  title="删除会话"
                  aria-label="删除会话"
                  @click.stop="handleDeleteSession(s.conversation_id, s.title)"
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="14"
                    height="14"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path
                      d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"
                    />
                    <path d="M10 11v6" />
                    <path d="M14 11v6" />
                    <path
                      d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- sb-toggle 半胶囊，严格 240/0 切换 -->
      <button
        type="button"
        class="sb-toggle"
        :style="{ left: showSidebar ? '240px' : '0px' }"
        :title="showSidebar ? '收起会话栏' : '展开会话栏'"
        aria-label="切换会话栏"
        @click="toggleSidebar"
      >
        <svg
          class="toggle-arrow"
          :class="{ flip: !showSidebar }"
          viewBox="0 0 24 24"
          width="12"
          height="12"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>

      <!-- 主区域：对话页 no-pad（内嵌滚动），其余页面维持 padding -->
      <main class="main-area" :class="{ 'no-pad': isConversationRoute }">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  height: 100vh;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-bg-app, #f7f5fb);
}

.workspace-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ── 顶栏 58px：严格 ai-report-dev 截图 ── */
.top-bar {
  height: 58px;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid
    var(--color-primary-border, rgba(111, 50, 155, 0.14));
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 24px;
}

.brand-area {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-logo {
  height: 28px;
  width: auto;
  display: block;
}

.brand-divider {
  width: 1px;
  height: 22px;
  background: var(--color-border, #e9e6ef);
}

.brand-copy {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  font-size: 18px;
  color: var(--color-text-dark, #102a43);
  letter-spacing: 0.3px;
}

.brand-copy-en {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-light, #9ca3af);
  letter-spacing: 0.4px;
}

.primary-nav {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.primary-nav-item {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 18px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-medium, #486581);
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
  cursor: pointer;
  font-family: inherit;
}

.primary-nav-item:hover:not(.disabled) {
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.primary-nav-item.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}

.primary-nav-item.disabled {
  color: var(--color-text-light, #9ca3af);
  opacity: 0.55;
  cursor: not-allowed;
}

.account-area {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.account-area .avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-light);
  color: var(--color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
}

.account-name {
  font-size: 13px;
  color: var(--color-text-medium);
  font-weight: 500;
}

.logout-button {
  border: 1px solid var(--color-border, #e4e1ea);
  background: #fff;
  color: var(--color-text-medium);
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s ease;
}

.logout-button:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* ── 侧边栏 240px 单态会话列表，严格 ai-report-dev ── */
.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--color-bg-sidebar, #faf8fc);
  border-right: 1px solid
    var(--color-primary-border, rgba(111, 50, 155, 0.14));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition:
    width 0.24s ease,
    border-right-width 0.24s ease;
  position: relative;
}

.sidebar.collapsed {
  width: 0;
  border-right: 0;
  padding: 0;
}

.sidebar-inner {
  width: 240px;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px 12px 12px;
  gap: 12px;
  overflow: hidden;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sidebar-section.sidebar-top {
  flex-shrink: 0;
}

.new-session-btn {
  width: 100%;
  height: 44px;
  border: 0;
  border-radius: 12px;
  background: var(--gradient-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-family: inherit;
  box-shadow: 0 4px 12px rgba(123, 63, 178, 0.22);
  transition: transform 0.12s ease, box-shadow 0.18s ease;
}

.new-session-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(123, 63, 178, 0.28);
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 38px;
  margin-top: 8px;
  padding: 0 12px;
  border-radius: 10px;
  color: var(--color-text-medium);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.14s ease, color 0.14s ease;
}

.sidebar-link:hover {
  background: var(--color-bg-hover);
  color: var(--color-primary);
}

.sidebar-link.active {
  background: var(--color-bg-active);
  color: var(--color-primary);
  font-weight: 600;
}

.sidebar-link-icon {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-light);
}

.sidebar-link:hover .sidebar-link-icon,
.sidebar-link.active .sidebar-link-icon {
  color: var(--color-primary);
}

.section-label {
  padding: 10px 12px 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--color-text-light, #627d98);
  text-transform: uppercase;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  min-height: 0;
  flex: 1;
}

.session-empty {
  padding: 10px 12px;
  font-size: 12px;
  color: var(--color-text-light, #9fb3c8);
  text-align: center;
}

.session-item-wrap {
  position: relative;
  display: flex;
  align-items: stretch;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 34px 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-medium, #486581);
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  position: relative;
  transition: background 0.12s, color 0.12s;
  min-width: 0;
  flex: 1;
  font-family: inherit;
}

.session-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-item:hover {
  background: var(--color-bg-hover, #f0ecf5);
  color: var(--color-text-dark, #102a43);
}

.session-item.active {
  background: var(--color-bg-active, #efeaf7);
  color: var(--color-primary, #7b3fb2);
  font-weight: 600;
}

.session-time {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--color-text-light, #9fb3c8);
  font-weight: 500;
}

.session-item.active .session-time {
  color: var(--color-primary);
  opacity: 0.75;
}

.session-delete {
  position: absolute;
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-light, #9fb3c8);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.12s,
    background 0.12s,
    color 0.12s;
}

.session-item-wrap:hover .session-delete,
.session-delete:focus-visible {
  opacity: 1;
}

.session-delete:hover {
  background: rgba(220, 53, 69, 0.08);
  color: #dc3545;
}

/* ── sb-toggle 半胶囊：top:74px 严格 ai-report-dev ── */
.sb-toggle {
  position: absolute;
  top: 74px;
  z-index: 30;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 32px;
  border: 1px solid
    var(--color-primary-border, rgba(111, 50, 155, 0.14));
  border-left: 0;
  border-radius: 0 8px 8px 0;
  background: #fff;
  color: var(--color-text-medium, #627d98);
  cursor: pointer;
  transition:
    left 0.24s ease,
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
  padding: 0;
  font-family: inherit;
}

.sb-toggle:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-color: var(--color-primary-border-strong);
}

.toggle-arrow {
  transition: transform 0.24s ease;
}

.toggle-arrow.flip {
  transform: rotate(180deg);
}

/* ── 主区域 ── */
.main-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 24px 28px 36px;
  background: var(--color-bg-app, #f7f5fb);
}

.main-area.no-pad {
  padding: 0;
  overflow: hidden;
}
</style>
