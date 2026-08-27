<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore, useConversationStore } from '../stores'
import type { ConversationSession } from '../types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const conversationStore = useConversationStore()

const LS_KEY = 'report-agent:sidebar-open-v1'
const showSidebar = ref(true)

const isConversationRoute = computed(
  () => route.name === 'conversations' || route.name === 'conversation-new' || route.name === 'conversation-detail',
)
const activeNav = computed(() => {
  return String(route.meta.nav || route.path.split('/')[1] || '')
})
const sessions = computed(() => conversationStore.sessions)
const currentSessionId = computed(() => {
  const id = route.params.sessionId as string | undefined
  return id ?? conversationStore.currentSessionId
})
const sortedSessions = computed(() => {
  return [...sessions.value].sort((a, b) => {
    const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0
    const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0
    return tb - ta
  })
})

function go(name: string) {
  router.push({ name })
}

async function handleNewConversation() {
  const s = await conversationStore.createSession('新会话')
  if (s) {
    await router.push({ name: 'conversation-detail', params: { sessionId: s.id } })
  } else {
    await router.push({ name: 'conversation-new' })
  }
}

function openSession(s: ConversationSession) {
  router.push({ name: 'conversation-detail', params: { sessionId: s.id } })
}

async function handleDeleteSession(sessionId: string, sessionTitle: string) {
  const ok = window.confirm(`确定删除会话「${sessionTitle || '新会话'}」吗？此操作不可撤销。`)
  if (!ok) return
  const wasActive = currentSessionId.value === sessionId && isConversationRoute.value
  await conversationStore.deleteSession(sessionId)
  if (wasActive) {
    await router.push({ name: 'conversation-new' })
  }
}

function formatTime(s: ConversationSession): string {
  if (!s.updated_at) return ''
  try {
    const d = new Date(s.updated_at)
    const today = new Date()
    const sameDay = d.toDateString() === today.toDateString()
    if (sameDay) {
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    }
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch {
    return ''
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(async () => {
  const saved = localStorage.getItem(LS_KEY)
  if (saved === '0') showSidebar.value = false
  try {
    await conversationStore.ensureSessionListLoaded()
  } catch {
    /* ignore — 后端暂无路由时 LS 兜底 */
  }
})

watch(showSidebar, (v) => {
  localStorage.setItem(LS_KEY, v ? '1' : '0')
})
</script>

<template>
  <div class="workspace">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="topbar-inner">
        <div class="topbar-left">
          <img class="logo" src="/logo.png" alt="光大银行" />
          <div class="brand">
            <h1 class="brand-title">智能报告工作台</h1>
          </div>
        </div>
        <div class="topbar-nav">
          <button type="button" class="nav-item" :class="{ active: activeNav === 'datasets' }" @click="go('datasets')">
            数据集
          </button>
          <button
            type="button"
            class="nav-item"
            :class="{ active: activeNav === 'tasks' }"
            @click="go('tasks')"
            title="任务记录列表接口待后端抵达"
          >
            任务记录
          </button>
          <button type="button" class="nav-item" :class="{ active: activeNav === 'analysis' }" @click="go('analysis')">
            分析
          </button>
          <button
            type="button"
            class="nav-item"
            :class="{ active: activeNav === 'reports' }"
            @click="handleNewConversation"
            title="对话式报告工作台"
          >
            报告任务
          </button>
          <button
            type="button"
            class="nav-item"
            :class="{ active: activeNav === 'capabilities' }"
            @click="go('capabilities')"
            title="能力目录接口待后端抵达"
          >
            能力目录
          </button>
        </div>
        <div class="topbar-right">
          <div class="user-chip">
            <span class="avatar">{{ auth.username?.[0] || 'A' }}</span>
            <span class="username">{{ auth.username || 'admin' }}</span>
          </div>
          <button type="button" class="logout-btn" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <div class="workspace-body">
      <!-- 侧边栏 sb-toggle anti-jitter -->
      <aside v-if="showSidebar" class="sidebar">
        <div class="sidebar-inner">
          <template v-if="isConversationRoute">
            <button type="button" class="primary-btn new-session-btn" @click="handleNewConversation">
              新报告对话
            </button>

            <div class="section-label">最近会话</div>
            <div class="session-list">
              <div v-if="sortedSessions.length === 0" class="session-empty">暂无会话，输入第一句话开始</div>
              <div
                v-for="s in sortedSessions"
                :key="s.id"
                class="session-item-wrap"
              >
                <button
                  type="button"
                  class="session-item"
                  :class="{ active: currentSessionId === s.id }"
                  @click="openSession(s)"
                  :title="s.title"
                >
                  <span class="nav-list-icon nav-list-icon-chat" aria-hidden="true">▤</span>
                  <span class="nav-list-label">{{ s.title }}</span>
                  <span class="session-time">{{ formatTime(s) }}</span>
                </button>
                <button
                  type="button"
                  class="session-delete"
                  title="删除会话"
                  aria-label="删除会话"
                  @click.stop="handleDeleteSession(s.id, s.title)"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                    <path d="M10 11v6" /><path d="M14 11v6" />
                    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                  </svg>
                </button>
              </div>
            </div>
          </template>

          <template v-else>
            <button type="button" class="primary-btn new-session-btn" @click="go('datasets')">
              数据集管理
            </button>

            <div class="nav-list">
              <button type="button" class="nav-list-item" :class="{ active: activeNav === 'datasets' }" @click="go('datasets')">
                <span class="nav-list-label">数据集</span>
              </button>
              <button type="button" class="nav-list-item" :class="{ active: activeNav === 'tasks' }" @click="go('tasks')">
                <span class="nav-list-label">任务记录</span>
                <span class="nav-badge beta" title="列表接口待后端抵达">占位</span>
              </button>
              <button type="button" class="nav-list-item" :class="{ active: activeNav === 'analysis' }" @click="go('analysis')">
                <span class="nav-list-label">数据分析</span>
              </button>
              <button
                type="button"
                class="nav-list-item"
                :class="{ active: activeNav === 'reports' }"
                @click="handleNewConversation"
              >
                <span class="nav-list-label">报告任务</span>
              </button>
              <button type="button" class="nav-list-item" :class="{ active: activeNav === 'capabilities' }" @click="go('capabilities')">
                <span class="nav-list-label">能力目录</span>
                <span class="nav-badge beta" title="能力目录接口待后端抵达">占位</span>
              </button>
            </div>
          </template>

          <div class="sidebar-spacer" />
        </div>
      </aside>

      <!-- sb-toggle button（固定 anti-jitter） -->
      <button
        type="button"
        class="sb-toggle"
        :class="{ open: showSidebar }"
        :title="showSidebar ? '收起侧边栏' : '展开侧边栏'"
        aria-label="toggle sidebar"
        @click="showSidebar = !showSidebar"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <polyline v-if="showSidebar" points="15 6 9 12 15 18" />
          <polyline v-else points="9 6 15 12 9 18" />
        </svg>
      </button>

      <!-- 主区域：唯一滚动条（或对话页内嵌无外滚动） -->
      <main class="main-area" :class="{ 'no-pad': isConversationRoute }">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--color-bg, #fafafc);
}

/* ── 顶栏 ── */
.topbar {
  flex-shrink: 0;
  height: 58px;
  background: #fff;
  border-bottom: 1px solid var(--color-border, #e9e6ef);
  z-index: 20;
}

.topbar-inner {
  height: 100%;
  max-width: 100%;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 24px;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.logo {
  height: 28px;
  width: auto;
  display: block;
}

.brand-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-dark, #1a2a43);
  margin: 0;
  letter-spacing: 0.5px;
}

.topbar-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  margin-right: auto;
}

.nav-item {
  border: 0;
  background: transparent;
  color: var(--color-text-medium, #5a6376);
  font-size: 14px;
  font-weight: 500;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: color 0.18s, background 0.18s;
}

.nav-item:hover:not(.disabled) {
  color: var(--color-primary);
  background: var(--color-primary-light);
}

.nav-item.active {
  color: var(--color-primary);
  background: var(--color-primary-light);
  font-weight: 600;
}

.nav-item.disabled {
  color: var(--color-text-light, #9ca3af);
  opacity: 0.55;
  cursor: not-allowed;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
}

.user-chip .avatar {
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

.user-chip .username {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-medium);
}

.logout-btn {
  border: 1px solid var(--color-border, #e4e1ea);
  background: #fff;
  color: var(--color-text-medium);
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.18s;
}

.logout-btn:hover {
  border-color: var(--color-primary-border-strong);
  color: var(--color-primary);
}

/* ── 主体布局 ── */
.workspace-body {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}

/* ── 侧边栏 anti-jitter：固定宽度 inner ── */
.sidebar {
  flex-shrink: 0;
  width: 240px;
  background: #fff;
  border-right: 1px solid var(--color-border, #e9e6ef);
  overflow: hidden;
  position: relative;
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

.new-session-btn {
  width: 100%;
  justify-content: center;
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
}

.session-item::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: transparent;
  transition: background 0.12s;
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

.session-item.active::before {
  background: var(--color-primary, #7b3fb2);
}

.nav-list-icon-chat {
  color: var(--color-primary);
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
  transition: opacity 0.12s, background 0.12s, color 0.12s;
}

.session-item-wrap:hover .session-delete,
.session-delete:focus-visible {
  opacity: 1;
}

.session-delete:hover {
  background: rgba(220, 53, 69, 0.08);
  color: #dc3545;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow: hidden;
}

.nav-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 0;
  background: transparent;
  border-radius: 10px;
  font-size: 14px;
  color: var(--color-text-medium, #5a6376);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: color 0.18s, background 0.18s;
  position: relative;
}

.nav-list-item:hover {
  background: var(--color-bg-hover, #f3f1f8);
  color: var(--color-text-dark);
}

.nav-list-item.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}

.nav-list-item.active::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--color-primary);
}

.nav-list-icon {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  line-height: 1;
}

.nav-list-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 7px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
  line-height: 1.4;
  flex-shrink: 0;
}
.nav-badge.beta {
  background: var(--color-bg-gray);
  color: var(--color-text-medium);
}

.sidebar-spacer {
  flex: 1;
  min-height: 0;
}

/* ── sb-toggle 半胶囊 ── */
.sb-toggle {
  position: absolute;
  left: 0;
  top: 80px;
  width: 16px;
  height: 32px;
  border: 1px solid var(--color-border, #e4e1ea);
  border-left: 0;
  border-radius: 0 10px 10px 0;
  background: #fff;
  color: var(--color-text-medium);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 15;
  transition: transform 0.24s ease, left 0.24s ease, color 0.18s, background 0.18s;
  font-family: inherit;
  padding: 0;
}

.sb-toggle.open {
  left: 240px;
}

.sb-toggle:hover {
  color: var(--color-primary);
  background: var(--color-primary-light);
}

/* ── 主内容区：对话模式下 0 padding 内嵌滚动，其他页面保留 24/28/36 ── */
.main-area {
  height: 100%;
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 24px 28px 36px;
}
.main-area.no-pad {
  padding: 0;
  overflow: hidden;
}

/* ── 主按钮 ── */
.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 11px 16px;
  border-radius: 10px;
  border: 0;
  background: var(--gradient-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  box-shadow: 0 2px 6px rgba(123, 63, 178, 0.18);
  transition: transform 0.12s, box-shadow 0.18s, opacity 0.18s;
}

.primary-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(123, 63, 178, 0.22);
}

.primary-btn:active:not(:disabled) {
  transform: translateY(0);
}

.primary-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
  box-shadow: none;
}
</style>
