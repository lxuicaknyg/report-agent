<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import type { PlanResponse, Task, TaskResult } from '../../types'
import { useConversationStore } from '../../stores/conversation'
import StepTimeline from '../plan/StepTimeline.vue'
import StreamContent from './StreamContent.vue'
import SlashCommandMenu, { type SlashCommandItem } from './SlashCommandMenu.vue'
import { useAllTaskStreams } from '../../composables/useAllTaskStreams'
import { sseClient } from '../../services/events'
import { taskApi, type SubmitTaskAttachmentRef } from '../../services/api'

type UploadKind = 'word' | 'pdf' | 'excel'

type LocalAttachment = {
  file_id: string
  filename: string
  kind: UploadKind
  size: number
}

const ACCEPT_MAP: Record<UploadKind, string> = {
  word: '.doc,.docx',
  pdf: '.pdf',
  excel: '.xls,.xlsx',
}

const KIND_LABEL: Record<UploadKind, string> = {
  word: 'Word 文档',
  pdf: 'PDF 文件',
  excel: 'Excel 表格',
}

const SLASH_COMMANDS: SlashCommandItem[] = [
  {
    id: 'generate-report',
    title: '生成报告',
    icon: 'report',
    description: '按模板结构自动规划章节 → 查询 → 生成带指标的完整 Markdown 报告',
    template:
      '请为我生成一份【报告主题】的分析报告。\n\n报告周期：2026 Q2（可修改）\n重点维度：\n- 维度 1（例：绿色信贷规模）\n- 维度 2（例：对公 vs 零售对比）\n- 维度 3（例：同比/环比变化）\n\n输出要求：\n1. 至少 6 个章节（背景、核心指标、结构拆解、趋势、风险、建议）\n2. 每个指标后注明口径\n3. 结尾给出 3 条可落地的业务建议\n4. 直接输出 Markdown，不要额外说明\n\n请开始规划：',
  },
  {
    id: 'polish-report',
    title: '润色报告',
    icon: 'polish',
    description: '把已有 Markdown / 草稿按专业金融报告风格重写：结构统一、数字格式化、结论先行',
    template:
      '请对下面这份报告草稿进行专业润色，保持数据、结论、章节名称 100% 不变，仅优化表达：\n\n【--- 粘贴你的 Markdown 草稿或章节内容 ---】\n\n润色要求：\n1) 结论先行：每个章节开头先给 1 句总结判断（↑↓持平/超预期/低于预期 …）\n2) 数字全部千分位格式化；同比/环比统一为「+12.3%」「-5.4%」；金额统一「人民币 X 亿元」\n3) 长句拆分，段落每段 ≤ 3 行\n4) 标题层级保持原 H2/H3 不变\n5) 删除口水话（"我们发现""可以看到"），直接陈述事实\n6) 全文用专业书面中文，无 emoji、无感叹号\n\n润色后直接输出 Markdown：',
  },
]

const props = defineProps<{
  plan: PlanResponse | null
  task: Task | null
  tasks: Task[]
}>()

const route = useRoute()
const conversationStore = useConversationStore()

const inputValue = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const composerRef = ref<HTMLDivElement | null>(null)

const submitFailed = ref(false)
let submitFailedHideTimer: ReturnType<typeof setTimeout> | null = null

function showSubmitFailedBanner() {
  submitFailed.value = true
  if (submitFailedHideTimer) clearTimeout(submitFailedHideTimer)
  submitFailedHideTimer = setTimeout(() => {
    submitFailed.value = false
    submitFailedHideTimer = null
  }, 4200)
}

function dismissSubmitFailed() {
  submitFailed.value = false
  if (submitFailedHideTimer) {
    clearTimeout(submitFailedHideTimer)
    submitFailedHideTimer = null
  }
}

const slashVisible = ref(false)
const slashQuery = ref('')
const slashStartPos = ref(-1)
const slashActiveIndex = ref(0)

const filteredSlashItems = computed<SlashCommandItem[]>(() => {
  const q = slashQuery.value.trim().toLowerCase()
  if (!q) return SLASH_COMMANDS
  return SLASH_COMMANDS.filter(
    (c) => c.title.toLowerCase().includes(q) || c.description.toLowerCase().includes(q),
  )
})

let slashHideTimer: ReturnType<typeof setTimeout> | null = null

function clearSlashHideTimer() {
  if (slashHideTimer) {
    clearTimeout(slashHideTimer)
    slashHideTimer = null
  }
}

function hideSlashMenu() {
  slashVisible.value = false
  slashQuery.value = ''
  slashStartPos.value = -1
  slashActiveIndex.value = 0
}

function handleInputChange() {
  const el = inputRef.value
  if (!el) return
  const text = inputValue.value
  const caret = el.selectionStart ?? text.length
  const before = text.slice(0, caret)
  const lastSlash = before.lastIndexOf('/')
  const isSlashAtStart =
    lastSlash === 0 || (lastSlash > 0 && /\s/.test(before.charAt(lastSlash - 1)))

  if (lastSlash === -1 || !isSlashAtStart) {
    if (slashVisible.value) hideSlashMenu()
    return
  }
  const query = before.slice(lastSlash + 1)
  if (/\s/.test(query)) {
    if (slashVisible.value) hideSlashMenu()
    return
  }
  if (!slashVisible.value) {
    slashVisible.value = true
    slashStartPos.value = lastSlash
    slashQuery.value = query
    slashActiveIndex.value = 0
  } else {
    slashQuery.value = query
    if (slashActiveIndex.value >= filteredSlashItems.value.length) {
      slashActiveIndex.value = Math.max(0, filteredSlashItems.value.length - 1)
    }
  }
}

function pickSlashItem(item: SlashCommandItem) {
  const el = inputRef.value
  if (!el) return
  const caret = el.selectionStart ?? inputValue.value.length
  const start = slashStartPos.value >= 0 ? slashStartPos.value : caret
  const before = inputValue.value.slice(0, start)
  const after = inputValue.value.slice(caret)
  const nextText = before + item.template + after
  inputValue.value = nextText
  hideSlashMenu()
  nextTick(() => {
    autoGrow()
    if (inputRef.value) {
      const insertEnd = before.length + item.template.length
      inputRef.value.focus()
      inputRef.value.setSelectionRange(insertEnd, insertEnd)
    }
  })
}

function handleComposerBlur() {
  clearSlashHideTimer()
  slashHideTimer = setTimeout(() => hideSlashMenu(), 160)
}

const expandedTasks = ref<Set<string>>(new Set())

const { getStream, handleSSEStreamingEvent, handleSSEStreamingCompleted, handleSSEStreamingFailed, cleanup } = useAllTaskStreams()

let unsubscribeStreaming: (() => void) | null = null

onMounted(() => {
  unsubscribeStreaming = sseClient.on('report.streaming', (event) => {
    const taskId = event.task_id
    const data = event.data as { content_delta?: string } | undefined
    if (taskId && data?.content_delta) {
      handleSSEStreamingEvent(taskId, data.content_delta)
    }
  })

  sseClient.on('text.chunk', (event) => {
    const taskId = event.task_id
    const data = event.data as { delta?: string } | undefined
    if (taskId && data?.delta) {
      handleSSEStreamingEvent(taskId, data.delta)
    }
  })

  sseClient.on('section.completed', (event) => {
    const taskId = event.task_id
    if (taskId) {
      handleSSEStreamingCompleted(taskId)
    }
  })

  sseClient.on('report.completed', (event) => {
    const taskId = event.task_id
    if (taskId) {
      handleSSEStreamingCompleted(taskId)
      cleanup(taskId)
    }
  })

  sseClient.on('task.failed', (event) => {
    const taskId = event.task_id
    if (taskId) {
      handleSSEStreamingFailed(taskId)
      cleanup(taskId)
    }
  })

  sseClient.on('task.cancelled', (event) => {
    const taskId = event.task_id
    if (taskId) {
      handleSSEStreamingFailed(taskId)
      cleanup(taskId)
    }
  })

  sseClient.on('task.completed', (event) => {
    const taskId = event.task_id
    if (taskId) {
      handleSSEStreamingCompleted(taskId)
      cleanup(taskId)
    }
  })

  nextTick(() => inputRef.value?.focus())
})

watch(() => route.params.sessionId, () => {
  nextTick(() => {
    inputRef.value?.focus()
    inputValue.value = ''
  })
}, { flush: 'post' })

onUnmounted(() => {
  if (unsubscribeStreaming) {
    unsubscribeStreaming()
  }
})

function toggleCollapse(taskId: string) {
  if (expandedTasks.value.has(taskId)) {
    expandedTasks.value.delete(taskId)
  } else {
    expandedTasks.value.add(taskId)
  }
}

function isExpanded(taskId: string): boolean {
  return expandedTasks.value.has(taskId)
}

const currentSessionId = computed(() => conversationStore.currentSessionId)

const orderedTasks = computed(() =>
  [...props.tasks]
    .filter((t) => t.conversation_id === currentSessionId.value)
    .sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      return ta - tb
    })
)

const examples = [
  '生成 2026 年一季度公司金融经营分析报告，重点关注绿色信贷',
  '快捷支付业务监测报告该包含哪些章节？',
  '净息差怎么算？',
]

const composerPlaceholder = computed(() => {
  return '描述你的数据分析需求，AI 将自动规划执行步骤'
})

/* ── 附件上传：+ 按钮（Word / PDF / Excel） ── */
const attachments = ref<LocalAttachment[]>([])
const uploadMenuVisible = ref(false)
const activeUploadKind = ref<UploadKind | null>(null)
const uploadInputRef = ref<HTMLInputElement | null>(null)
let uploadMenuHideTimer: ReturnType<typeof setTimeout> | null = null

function clearUploadMenuHideTimer() {
  if (uploadMenuHideTimer) {
    clearTimeout(uploadMenuHideTimer)
    uploadMenuHideTimer = null
  }
}

function scheduleHideUploadMenu() {
  clearUploadMenuHideTimer()
  uploadMenuHideTimer = window.setTimeout(() => hideUploadMenu(), 160)
}

function handlePlusBtnBlur() {
  scheduleHideUploadMenu()
}

function hideUploadMenu() {
  uploadMenuVisible.value = false
  activeUploadKind.value = null
}

function openUploadForKind(kind: UploadKind) {
  activeUploadKind.value = kind
  hideUploadMenu()
  nextTick(() => {
    if (uploadInputRef.value) {
      uploadInputRef.value.accept = ACCEPT_MAP[kind]
      uploadInputRef.value.value = ''
      uploadInputRef.value.click()
    }
  })
}

function toggleUploadMenu() {
  if (uploadMenuVisible.value) {
    hideUploadMenu()
    return
  }
  clearUploadMenuHideTimer()
  uploadMenuVisible.value = true
}

function handleFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const kind = activeUploadKind.value
  for (let i = 0; i < input.files.length; i += 1) {
    const f = input.files[i]
    attachments.value.push({
      file_id: `local_${Date.now()}_${i.toString().padStart(3, '0')}`,
      filename: f.name,
      kind: kind ?? detectKindByFilename(f.name),
      size: f.size,
    })
  }
  nextTick(() => scrollToBottom())
}

function detectKindByFilename(name: string): UploadKind {
  const ext = name.toLowerCase()
  if (ext.endsWith('.pdf')) return 'pdf'
  if (ext.endsWith('.xls') || ext.endsWith('.xlsx')) return 'excel'
  return 'word'
}

function removeAttachment(fileId: string) {
  attachments.value = attachments.value.filter((a) => a.file_id !== fileId)
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function currentAcceptStr(): string {
  const s = new Set<string>()
  for (const v of Object.values(ACCEPT_MAP)) {
    v.split(',').forEach((x) => s.add(x))
  }
  return [...s].join(',')
}

watch([() => props.tasks], async () => {
  await nextTick()
  scrollToBottom()
}, { deep: true })

async function handleSend() {
  const content = inputValue.value.trim()
  if ((!content && attachments.value.length === 0) || conversationStore.isSending) return

  if (!conversationStore.currentSessionId) {
    await conversationStore.createSession('新会话')
  }

  const sessionIdBefore = conversationStore.currentSessionId
  const apiAttachments: SubmitTaskAttachmentRef[] = attachments.value.map((a) => ({
    file_id: a.file_id,
    filename: a.filename,
    kind: a.kind,
  }))
  const prompt = content
    ? content
    : (apiAttachments.length > 0
      ? `附件：${apiAttachments.map((a) => a.filename).join('、')}`
      : '')
  const task = await conversationStore.sendMessage(prompt, { attachments: apiAttachments })
  attachments.value = []
  inputValue.value = ''
  await nextTick(() => autoGrow())
  scrollToBottom()

  if (sessionIdBefore && conversationStore.currentSessionId === sessionIdBefore) {
    conversationStore.updateConversationTitle(
      sessionIdBefore,
      content || prompt,
    )
  }

  if (!task) {
    showSubmitFailedBanner()
    return
  }

  sseClient.connect(task.id)
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (slashVisible.value) {
    const items = filteredSlashItems.value
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (items.length === 0) return
      slashActiveIndex.value = (slashActiveIndex.value + 1) % items.length
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (items.length === 0) return
      slashActiveIndex.value = (slashActiveIndex.value - 1 + items.length) % items.length
      return
    }
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault()
      const item = items[slashActiveIndex.value]
      if (item) pickSlashItem(item)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      hideSlashMenu()
      return
    }
    if (event.key === 'Tab') {
      const item = items[slashActiveIndex.value]
      if (item) {
        event.preventDefault()
        pickSlashItem(item)
        return
      }
    }
  }
  if (uploadMenuVisible.value) {
    if (event.key === 'Escape') {
      event.preventDefault()
      hideUploadMenu()
      return
    }
  }
  if (event.key === 'Escape') {
    if (inputRef.value) {
      inputRef.value.blur()
    }
    return
  }
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    handleSend()
  }
}

function autoGrow() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function taskStatusText(status: string): string {
  const map: Record<string, string> = {
    created: '等待开始',
    planning: '规划中',
    running: '执行中',
    needs_data: '等待数据',
    completed: '已完成',
    failed: '执行失败',
    cancelled: '已中止',
  }
  return map[status] ?? status
}

function hasResultData(result: TaskResult | null): boolean {
  if (!result) return false
  return Object.keys(result).length > 0
}

function formatResultValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'number') return value.toLocaleString('zh-CN')
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value ? '是' : '否'
  return JSON.stringify(value)
}

async function abortTask(taskId: string) {
  try {
    await taskApi.cancelTask(taskId)
  } catch {
    // ignore network errors
  }
}

function isExpandableSection(key: string): boolean {
  const skip = ['summary', 'statistics', 'overview', 'total', 'report_id', 'title', 'cited_metrics', 'cited_sections', 'sub_type', 'body_markdown', 'followup_suggestions']
  return !skip.includes(key) && typeof key === 'string'
}

function getFollowupSuggestions(task: Task): string[] {
  const r = task.result as TaskResult | null
  const raw = r?.followup_suggestions ?? []
  if (Array.isArray(raw)) {
    return raw
      .map(x => (typeof x === 'string' ? x : (x && typeof x === 'object' && 'text' in x ? String((x as Record<string, unknown>).text) : '')))
      .filter(x => x && x.trim().length > 0)
  }
  return []
}

function handleFollowupClick(question: string) {
  if (!question || !question.trim()) return
  inputValue.value = question.trim()
  nextTick(() => {
    autoGrow()
    if (inputRef.value) {
      inputRef.value.focus()
      const len = inputRef.value.value.length
      inputRef.value.setSelectionRange(len, len)
    }
  })
}

function pickExampleChip(text: string) {
  if (!text || !text.trim()) return
  inputValue.value = text.trim()
  nextTick(() => {
    autoGrow()
    if (inputRef.value) {
      inputRef.value.focus()
      const len = inputRef.value.value.length
      inputRef.value.setSelectionRange(len, len)
    }
  })
}
</script>

<template>
  <div class="chat-panel">
    <div
      v-if="submitFailed"
      class="submit-failed-banner"
      role="alert"
    >
      <span class="submit-failed-text">后端对话服务暂未上线（404），请稍后再试或联系管理员部署接口。</span>
      <button type="button" class="submit-failed-close" aria-label="关闭提示" @click="dismissSubmitFailed">×</button>
    </div>
    <div ref="messagesContainer" class="chat-scroll">
      <div class="chat-inner">
        <!-- 空态：欢迎语 -->
        <div v-if="orderedTasks.length === 0" class="welcome">
          <h1 class="welcome-title">智能数据分析助手</h1>
          <p class="welcome-subtitle">描述你的需求，AI 将自动规划执行步骤并生成分析报告</p>
          <div class="welcome-chips">
            <button
              v-for="ex in examples"
              :key="ex"
              type="button"
              class="welcome-chip"
              @click="pickExampleChip(ex)"
            >{{ ex }}</button>
          </div>
        </div>

        <!-- 任务历史 -->
        <div v-for="task in orderedTasks" :key="task.id" class="task-flow">
          <!-- 用户输入气泡 -->
          <div class="msg-row is-user">
            <div class="bubble user-bubble">
              <div class="user-text">{{ task.prompt }}</div>
            </div>
          </div>

          <!-- 助手回复 -->
          <div class="msg-row is-assistant">
            <div class="assistant-stack">
              <div
                v-if="task.plan || task.status === 'created' || task.status === 'planning' || task.status === 'running'"
                class="thought-card"
              >
                <button type="button" class="thought-head" @click="toggleCollapse(task.id)">
                  <span class="ac-bar" aria-hidden="true" />
                  <span class="ac-title">执行计划</span>
                  <span class="thought-badge" :class="task.status">{{ taskStatusText(task.status) }}</span>
                  <svg
                    class="thought-chevron"
                    :class="{ open: isExpanded(task.id) }"
                    viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
                <div v-if="isExpanded(task.id)" class="thought-body">
                  <div v-if="task.plan" class="ac-goal">
                    <div class="ac-goal-label">任务目标</div>
                    <div class="ac-goal-text">{{ task.plan.summary }}</div>
                  </div>
                  <div v-else-if="task.status === 'created' || task.status === 'planning'" class="ac-goal">
                    <div class="ac-goal-label muted flex-row">
                      <span>正在规划执行步骤</span>
                      <span class="loading-dots" aria-hidden="true">
                        <span /><span /><span />
                      </span>
                    </div>
                  </div>
                  <div v-if="task.plan && task.plan.steps.length > 0" class="ac-timeline">
                    <StepTimeline :steps="task.plan.steps" />
                  </div>
                </div>
              </div>

              <!-- 回答气泡（流式中 + 已完成回答 + 中止内容都走这里，无大标题，直接正文） -->
              <div
                v-if="
                  (task.status === 'running' && getStream(task.id).chunks.length > 0) ||
                  (task.status === 'completed' && (hasResultData(task.result as TaskResult) || getStream(task.id).chunks.length > 0)) ||
                  (task.status === 'cancelled' && getStream(task.id).chunks.length > 0)
                "
                class="answer-bubble"
              >
                <StreamContent
                  :chunks="(
                    getStream(task.id).chunks.length > 0
                      ? getStream(task.id).chunks
                      : [(task.result as TaskResult)?.summary ?? (task.plan?.steps ?? []).map((s) => s.result?.body_markdown ?? '').join('')] as string[]
                  ).filter((c) => c)"
                  :streaming="task.status === 'running' && getStream(task.id).isStreaming"
                />

                <!-- 报告模式的统计指标（Consult 模式一般为 null，保留兼容三栏报告） -->
                <div v-if="(task.result as TaskResult)?.statistics" class="ac-stats">
                  <div v-for="(value, key) in (task.result as TaskResult).statistics" :key="String(key)" class="ac-stat">
                    <span class="ac-stat-label">{{ String(key) }}</span>
                    <span class="ac-stat-value">{{ formatResultValue(value) }}</span>
                  </div>
                </div>

                <!-- 「你可能还想问」Followup chips（cited_metrics/cited_sections 已移除，不渲染） -->
                <div
                  v-if="task.status === 'completed' && getFollowupSuggestions(task).length > 0"
                  class="followup-wrap"
                >
                  <div class="followup-label">你可能还想问</div>
                  <div class="followup-chips">
                    <button
                      v-for="q in getFollowupSuggestions(task)"
                      :key="q"
                      type="button"
                      class="followup-chip"
                      @click="handleFollowupClick(q)"
                    >{{ q }}</button>
                  </div>
                </div>
              </div>

              <!-- 完成无结果 -->
              <div v-if="task.status === 'completed' && !hasResultData(task.result as TaskResult) && getStream(task.id).chunks.length === 0" class="answer-bubble answer-empty">
                <div class="ac-result-text">任务已完成</div>
              </div>

              <!-- 错误卡片 -->
              <div v-if="task.status === 'failed' && task.error" class="error-card">
                <div class="error-head">
                  <span class="ac-bar error" />
                  <span class="ac-title">执行失败</span>
                </div>
                <div class="ac-body">
                  <div class="ac-error-text">{{ task.error }}</div>
                </div>
              </div>

              <!-- 中止卡片（无流式内容的情况） -->
              <div v-if="task.status === 'cancelled' && getStream(task.id).chunks.length === 0" class="answer-bubble answer-empty">
                <div class="ac-error-text">任务已被用户中止</div>
              </div>
              <div v-if="task.status === 'cancelled' && getStream(task.id).chunks.length > 0" class="cancelled-hint">
                生成已被中止，以上为已输出的内容。
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div ref="composerRef" class="composer" style="position: relative;">
      <SlashCommandMenu
        v-if="slashVisible"
        :items="filteredSlashItems"
        :active-index="slashActiveIndex"
        @pick="pickSlashItem"
      />
      <div
        v-if="uploadMenuVisible"
        class="upload-menu"
      >
        <button
          type="button"
          class="upload-menu-item"
          @click="openUploadForKind('word')"
        >
          <span class="upload-menu-icon word">W</span>
          <div class="upload-menu-meta">
            <div class="upload-menu-title">上传 Word 文档</div>
            <div class="upload-menu-desc">.doc / .docx</div>
          </div>
        </button>
        <button
          type="button"
          class="upload-menu-item"
          @click="openUploadForKind('pdf')"
        >
          <span class="upload-menu-icon pdf">P</span>
          <div class="upload-menu-meta">
            <div class="upload-menu-title">上传 PDF 文件</div>
            <div class="upload-menu-desc">.pdf</div>
          </div>
        </button>
        <button
          type="button"
          class="upload-menu-item"
          @click="openUploadForKind('excel')"
        >
          <span class="upload-menu-icon excel">X</span>
          <div class="upload-menu-meta">
            <div class="upload-menu-title">上传 Excel 表格</div>
            <div class="upload-menu-desc">.xls / .xlsx</div>
          </div>
        </button>
      </div>
      <input
        ref="uploadInputRef"
        type="file"
        style="display: none;"
        :accept="currentAcceptStr()"
        multiple
        @change="handleFilesSelected"
      />
      <div class="composer-inner">
        <button
          type="button"
          class="plus-btn"
          :class="{ active: uploadMenuVisible }"
          @click="toggleUploadMenu"
          @focus="clearUploadMenuHideTimer()"
          @blur="handlePlusBtnBlur"
          aria-label="添加附件"
          title="添加附件"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
        <div class="composer-input-wrap">
          <div v-if="attachments.length > 0" class="attachment-chips">
            <div
              v-for="a in attachments"
              :key="a.file_id"
              class="attachment-chip"
            >
              <span class="attachment-icon" :class="a.kind">
                {{ a.kind === 'word' ? 'W' : a.kind === 'pdf' ? 'P' : 'X' }}
              </span>
              <div class="attachment-meta">
                <span class="attachment-name" :title="a.filename">{{ a.filename }}</span>
                <span class="attachment-size">{{ formatFileSize(a.size) }} · {{ KIND_LABEL[a.kind] }}</span>
              </div>
              <button
                type="button"
                class="attachment-remove"
                aria-label="移除附件"
                title="移除附件"
                @click.stop="removeAttachment(a.file_id)"
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>
          <textarea
            ref="inputRef"
            v-model="inputValue"
            class="composer-input"
            :placeholder="composerPlaceholder"
            rows="1"
            @keydown="handleKeydown"
            @input="handleInputChange(); autoGrow()"
            @focus="clearSlashHideTimer()"
            @blur="handleComposerBlur"
          />
        </div>
        <button
          class="send-btn"
          @click="handleSend"
          :disabled="conversationStore.isSending || (!inputValue.trim() && attachments.length === 0)"
        >
          <span v-if="conversationStore.isSending" class="spinner-small" />
          <span v-else>发送</span>
        </button>
      </div>
    </div>

    <p class="disclaimer">
      请勿上传或处理敏感、涉密数据。本平台内容由 AI 生成，仅供参考。
    </p>
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-width: 960px;
  margin: 0 auto;
  width: 100%;
  background: var(--color-bg-app, #f7f5fb);
}

.chat-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 20px 12px;
}

.chat-inner {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 空态 ── */
.welcome {
  margin-top: 6vh;
  text-align: center;
}

.welcome-title {
  margin: 0 0 10px;
  font-size: 26px;
  font-weight: 700;
  color: var(--color-text-dark);
  letter-spacing: -0.3px;
}

.welcome-subtitle {
  margin: 0 0 28px;
  font-size: 14px;
  color: var(--color-text-light);
}

.welcome-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 720px;
  margin: 0 auto;
}

.welcome-chip {
  padding: 10px 16px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-pill);
  background: #fff;
  color: var(--color-text-medium);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s;
}

.welcome-chip:hover {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* ── 任务流 ── */
.task-flow {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.msg-row {
  display: flex;
}

.msg-row.is-user {
  justify-content: flex-end;
}

.msg-row.is-assistant {
  justify-content: flex-start;
}

/* ── 用户气泡 ── */
.bubble {
  max-width: 82%;
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.6;
  border-radius: 16px;
  word-break: break-word;
  box-shadow: 0 1px 2px rgba(16, 42, 67, 0.06);
}

.user-bubble {
  background: var(--gradient-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
  white-space: pre-wrap;
}

.user-text {
  white-space: pre-wrap;
}

/* ── 助手卡片堆叠 ── */
.assistant-stack {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ac-stack {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── 执行计划折叠卡（保持原 ac-head 竖线+粗字样式） ── */
.thought-card {
  width: 100%;
  display: flex;
  flex-direction: column;
}

.thought-head {
  width: 100%;
  border: 1px solid var(--color-primary-border);
  background: #fff;
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}

.thought-head .ac-bar {
  flex-shrink: 0;
}

.thought-head .ac-title {
  flex: 1;
}

.thought-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--color-bg-hover, #f0ecf5);
  color: var(--color-text-medium);
}

.thought-badge.planning,
.thought-badge.running,
.thought-badge.created,
.thought-badge.needs_data {
  color: var(--color-primary);
  background: var(--color-primary-light);
}

.thought-badge.completed {
  color: var(--color-success, #059669);
  background: var(--color-success-bg, #ecfdf5);
}

.thought-badge.failed {
  color: var(--color-error, #dc2626);
  background: var(--color-error-bg, #fef2f2);
}

.thought-badge.cancelled {
  color: var(--color-text-light);
  background: var(--color-bg-hover, #f0ecf5);
}

.thought-chevron {
  flex-shrink: 0;
  color: var(--color-text-light);
  transition: transform 0.2s ease;
}

.thought-chevron.open {
  transform: rotate(180deg);
}

.thought-body {
  padding: 4px 12px 12px;
  background: #fff;
  border-radius: 0 0 12px 12px;
  border: 1px solid var(--color-primary-border);
  border-top: none;
  margin: -1px 0 0;
}

.thought-body .ac-goal {
  margin-top: 12px;
}

/* ── 回答气泡 ── */
.answer-bubble {
  background: #fff;
  border: 1px solid var(--color-primary-border);
  border-radius: 16px;
  border-top-left-radius: 4px;
  padding: 14px 16px;
  line-height: 1.7;
  font-size: 14px;
  color: var(--color-text-dark);
  box-shadow: 0 1px 2px rgba(16, 42, 67, 0.05);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.answer-bubble.answer-empty {
  padding: 12px 16px;
  color: var(--color-text-light);
}

/* ── 你可能还想问 Followup ── */
.followup-wrap {
  margin-top: 2px;
  padding-top: 12px;
  border-top: 1px solid var(--color-primary-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.followup-label {
  font-size: 12px;
  color: var(--color-text-light);
  font-weight: 500;
}

.followup-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.followup-chip {
  flex-shrink: 0;
  padding: 6px 14px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-pill);
  background: #fff;
  color: var(--color-text-medium);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
  line-height: 1.5;
}

.followup-chip:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-color: var(--color-primary);
}

/* ── 错误/中止卡片 ── */
.error-card {
  background: #fff;
  border: 1px solid var(--color-error, #dc2626);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cancelled-hint {
  font-size: 12px;
  color: var(--color-text-light);
  padding: 2px 4px;
  line-height: 1.5;
}

.ac-card {
  background: #fff;
  border: 1px solid var(--color-primary-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(16, 42, 67, 0.06);
}

/* 卡片头部 */
.ac-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(111, 50, 155, 0.06);
}

.ac-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ac-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ac-bar {
  width: 3px;
  height: 16px;
  border-radius: 2px;
  background: var(--color-primary);
}

.ac-bar.success {
  background: var(--color-success, #059669);
}

.ac-bar.error {
  background: var(--color-error, #dc2626);
}

.ac-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-dark);
}

/* 状态徽章 */
.ac-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 12px;
  border-radius: var(--radius-pill);
  background: var(--color-bg-hover, #f0ecf5);
  color: var(--color-text-medium);
}

.ac-badge.planning,
.ac-badge.running,
.ac-badge.created,
.ac-badge.needs_data {
  color: var(--color-primary);
  background: var(--color-primary-light);
}

.ac-badge.completed {
  color: var(--color-success, #059669);
  background: var(--color-success-bg, #ecfdf5);
}

.ac-badge.failed {
  color: var(--color-error, #dc2626);
  background: var(--color-error-bg, #fef2f2);
}

.ac-badge.cancelled {
  color: var(--color-text-light);
  background: var(--color-bg-hover, #f0ecf5);
}

.ac-cancelled-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-text-light);
}

/* 折叠按钮 */
.ac-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-text-light);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s ease, color 0.15s ease;
}

.ac-chevron:hover {
  background: var(--color-bg-hover, #f0ecf5);
  color: var(--color-text-dark);
}

/* 中止按钮 */
.ac-abort-btn {
  margin-left: 8px;
  padding: 3px 10px;
  border: 1px solid var(--color-error, #dc2626);
  background: transparent;
  color: var(--color-error, #dc2626);
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ac-abort-btn:hover {
  background: var(--color-error, #dc2626);
  color: #fff;
}

/* 卡片主体 */
.ac-body {
  padding: 0 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ac-goal {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: var(--color-primary-light);
  border-radius: 8px;
  margin-top: 12px;
}

.ac-goal-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
}

.ac-goal-label.muted {
  color: var(--color-text-light);
}

.flex-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.loading-dots {
  display: inline-flex;
  gap: 4px;
  line-height: 1;
}

.loading-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-primary);
  opacity: 0.25;
  animation: loading-dots-bounce 1.2s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes loading-dots-bounce {
  0%, 80%, 100% {
    opacity: 0.2;
    transform: scale(0.9);
  }
  40% {
    opacity: 1;
    transform: scale(1.15);
  }
}

.submit-failed-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 20px 0;
  padding: 10px 14px;
  background: #fff7ed;
  border: 1px solid #fdba74;
  border-radius: 10px;
  flex-shrink: 0;
}

.submit-failed-text {
  flex: 1;
  font-size: 13px;
  color: #9a3412;
  line-height: 1.5;
}

.submit-failed-close {
  flex-shrink: 0;
  background: transparent;
  border: none;
  color: #9a3412;
  font-size: 20px;
  line-height: 1;
  padding: 0 4px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.15s;
  font-family: inherit;
}

.submit-failed-close:hover {
  opacity: 1;
}

.ac-goal-text {
  font-size: 14px;
  color: var(--color-text-dark);
  line-height: 1.5;
}

.ac-timeline {
  display: flex;
  flex-direction: column;
  margin-top: 4px;
}

/* 结果区 */
.ac-result-text {
  font-size: 14px;
  color: var(--color-text-dark);
  line-height: 1.6;
  padding: 4px 0;
}

.ac-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

.ac-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  background: var(--color-primary-light);
  border-radius: 6px;
}

.ac-stat-label {
  font-size: 12px;
  color: var(--color-text-light);
}

.ac-stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.ac-details {
  border-top: 1px solid var(--color-primary-border);
  padding-top: 8px;
}

.ac-details-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-dark);
  padding: 6px 0;
  cursor: pointer;
  list-style: none;
}

.ac-details-summary::-webkit-details-marker {
  display: none;
}

.ac-details-toggle {
  font-size: 12px;
  color: var(--color-text-lighter);
}

.ac-details-content {
  padding: 8px 10px;
  background: var(--color-primary-light);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ac-details-item {
  padding: 4px 0;
  border-bottom: 1px solid var(--color-primary-border);
}

.ac-details-item:last-child {
  border-bottom: none;
}

.ac-field {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  padding: 2px 0;
}

.ac-field-label {
  color: var(--color-text-light);
  flex-shrink: 0;
  max-width: 40%;
}

.ac-field-value {
  color: var(--color-text-dark);
  text-align: right;
  word-break: break-word;
}

.ac-error-text {
  font-size: 13px;
  color: var(--color-error, #dc2626);
  line-height: 1.5;
  padding: 4px 0;
}

/* ── 输入区 ── */
.composer {
  flex-shrink: 0;
  padding: 10px 16px 4px;
  background: var(--color-bg-app, #f7f5fb);
}

.composer-inner {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 8px;
  border: 1px solid var(--color-primary-border);
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(16, 42, 67, 0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.composer-inner:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 2px 12px rgba(123, 63, 178, 0.1);
}

.plus-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: 1px solid var(--color-primary-border);
  background: #fff;
  color: var(--color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s;
  font-family: inherit;
}

.plus-btn:hover,
.plus-btn.active {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
}

.composer-input-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 6px;
}

.attachment-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px 6px 8px;
  border: 1px solid var(--color-primary-border);
  border-radius: 10px;
  background: var(--color-primary-light);
  max-width: 100%;
}

.attachment-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.attachment-icon.word { background: #2b579a; }
.attachment-icon.pdf { background: #c53030; }
.attachment-icon.excel { background: #16803d; }

.attachment-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}

.attachment-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-dark);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}

.attachment-size {
  font-size: 10px;
  color: var(--color-text-light);
}

.attachment-remove {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border: 0;
  background: transparent;
  border-radius: 6px;
  color: var(--color-text-light);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
  font-family: inherit;
}

.attachment-remove:hover {
  background: rgba(220, 53, 69, 0.1);
  color: #dc3545;
}

.upload-menu {
  position: absolute;
  left: 16px;
  bottom: calc(100% + 10px);
  width: 300px;
  background: #fff;
  border: 1px solid var(--color-primary-border);
  border-radius: 14px;
  box-shadow: 0 12px 32px rgba(16, 42, 67, 0.12);
  padding: 6px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.upload-menu-item {
  width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  transition: background 0.12s;
  text-align: left;
  font-family: inherit;
}

.upload-menu-item:hover {
  background: var(--color-primary-light);
}

.upload-menu-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.upload-menu-icon.word { background: #2b579a; }
.upload-menu-icon.pdf { background: #c53030; }
.upload-menu-icon.excel { background: #16803d; }

.upload-menu-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.upload-menu-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.upload-menu-desc {
  font-size: 11px;
  color: var(--color-text-light);
}

.composer-input {
  flex: 1;
  border: 0;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text-dark);
  background: transparent;
  max-height: 160px;
  padding: 6px 0;
  font-family: inherit;
}

.composer-input::placeholder {
  color: var(--color-text-lighter);
}

.send-btn {
  flex-shrink: 0;
  padding: 9px 22px;
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--gradient-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease, box-shadow 0.15s;
}

.send-btn:hover:not(:disabled) {
  box-shadow: 0 4px 14px rgba(123, 63, 178, 0.3);
}

.send-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.spinner-small {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  vertical-align: middle;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ── 合规提醒 ── */
.disclaimer {
  flex-shrink: 0;
  margin: 0;
  padding: 4px 12px 10px;
  text-align: center;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-lighter);
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .chat-scroll {
    padding: 16px 12px 8px;
  }

  .bubble {
    max-width: 90%;
  }

  .welcome-title {
    font-size: 22px;
  }
}
</style>
