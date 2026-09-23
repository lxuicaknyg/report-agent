<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Message, QuestionResolutionInput } from '../../types'
import { useConversationStore } from '../../stores/conversation'
import SlashCommandMenu, { type SlashCommandItem } from './SlashCommandMenu.vue'
import PlanCard from './messages/PlanCard.vue'
import ProgressFlow from './messages/ProgressFlow.vue'
import QuestionCard from './messages/QuestionCard.vue'
import ReportCard from './messages/ReportCard.vue'
import { renderMarkdown } from '../../utils/markdown'

type UploadKind = 'word' | 'excel'

type LocalAttachment = {
  file_id: string
  filename: string
  kind: UploadKind
  size: number
  file: File
}

const ACCEPT_MAP: Record<UploadKind, string> = {
  word: '.docx,.md,.markdown,.txt',
  excel: '.xlsx',
}

const KIND_LABEL: Record<UploadKind, string> = {
  word: '报告模板',
  excel: 'Excel 表格',
}

const SLASH_COMMANDS: SlashCommandItem[] = [
  {
    id: 'generate-report',
    title: '生成报告',
    icon: 'report',
    description: '按模板结构自动规划章节 → 查询 → 生成带指标的完整报告',
    template:
      '请为我生成一份【报告主题】的分析报告。\n\n报告周期：2026 Q2（可修改）\n重点维度：\n- 维度 1（例：绿色信贷规模）\n- 维度 2（例：对公 vs 零售对比）\n\n输出要求：\n1. 每个指标后注明口径\n2. 结尾给出 3 条可落地的业务建议',
  },
]

const EXAMPLES = [
  '生成 2026 年一季度公司金融经营分析报告，重点关注绿色信贷',
  '快捷支付业务监测报告该包含哪些章节？',
  '净息差怎么算？',
]

const store = useConversationStore()

const inputValue = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const attachments = ref<LocalAttachment[]>([])

/* ── 消息渲染 ── */

const messages = computed(() => store.messages)

/** Chapter state straight from the session, driving the live generation flow. */
const liveProgress = computed(() => {
  const session = store.reportSession
  const planned = session?.plan?.chapters
  if (!planned?.length) return null
  const drafts = session?.chapter_drafts ?? {}
  const waiting = new Set(
    (session?.pending_questions ?? []).map((question) => question.chapter_id).filter(Boolean),
  )
  // 停下来的跑不再有「正在写的那一章」。后端刻意保留 current_chapter_id 用于续跑，
  // 所以这里必须看会话状态，否则停止后那一章会一直转着「正在生成中」。
  const halted = session?.status === 'cancelled' || session?.status === 'failed'
  return planned.map((chapter) => {
    const draft = drafts[chapter.section_id]
    const atChapter = session?.current_chapter_id === chapter.section_id
    const status = draft
      ? 'completed'
      : waiting.has(chapter.section_id)
        ? 'waiting_user'
        : atChapter
          ? (halted ? 'stopped' : 'running')
          : 'pending'
    return {
      section_id: chapter.section_id,
      title: chapter.title,
      completed: Boolean(draft),
      status,
      content: draft?.content,
    } as const
  })
})

/** Questions still open, so the card knows whether it is editable. */
const pendingQuestionIds = computed(
  () => (store.reportSession?.pending_questions ?? []).map((item) => item.question_id),
)

/** How each question was settled, for the read-only view after submission. */
const resolvedQuestions = computed(() =>
  Object.fromEntries(
    (store.reportSession?.resolved_questions ?? []).map((item) => [item.question_id, item]),
  ),
)

/** Question cards already submitted in this session, by the message they belong to.
 *
 * The POST returns as soon as the turn is stored and the run continues in the
 * background, so the button would re-enable while the backend is still working
 * and a second click would hit questions that are already consumed. A card is
 * answered exactly once, so latch it locally instead of waiting for the poll.
 */
const submittedQuestions = ref(new Set<string>())

async function submitResolutions(messageId: string, resolutions: QuestionResolutionInput[]) {
  if (submittedQuestions.value.has(messageId)) return
  submittedQuestions.value = new Set(submittedQuestions.value).add(messageId)
  const dropped = resolutions.filter((item) => item.action === 'drop').length
  const supplied = resolutions.length - dropped
  const sent = await store.sendMessage({
    text: `已处理本章 ${resolutions.length} 个待补充项：补充 ${supplied} 项，删除 ${dropped} 项`,
    resolutions,
  })
  if (!sent) {
    const next = new Set(submittedQuestions.value)
    next.delete(messageId)
    submittedQuestions.value = next
    return
  }
  await nextTick(() => scrollToBottom())
}

/** Only the newest progress turn renders.
 *
 * A run that pauses for data emits one progress message per resumption, each
 * carrying the full chapter list, so rendering them all repeats the same
 * timeline several times over. The newest one subsumes the rest, which keeps
 * planning → writing → questions → download reading as a single flow.
 */
function isLatestProgress(message: Message, index: number): boolean {
  return message.kind === 'progress'
    && !messages.value.slice(index + 1).some((item) => item.kind === 'progress')
}

/** 建议 chip 只出现在最新一条、且仍待确认的计划上：历史版本和已开工的计划都只读。 */
function isSuggestablePlan(message: Message, index: number): boolean {
  if (message.kind !== 'plan') return false
  if (store.reportSession?.plan?.status !== 'awaiting_confirmation') return false
  const later = messages.value.slice(index + 1)
  return !later.some((item) => item.kind === 'plan') && !store.isAwaitingAssistant
}

/** What the backend is busy with, so the waiting state is never a blank spinner. */
const thinkingLabel = computed(() => {
  const session = store.reportSession
  const last = messages.value[messages.value.length - 1]
  if (session?.status === 'running') {
    const chapters = session.plan?.chapters ?? []
    const done = Object.keys(session.chapter_drafts ?? {}).length
    return chapters.length
      ? `正在生成章节 ${Math.min(done + 1, chapters.length)}/${chapters.length}…`
      : '正在生成章节…'
  }
  if (last?.role === 'user') {
    if (last.attachments.length) return '正在解析模板与数据，规划章节…'
    // The backend tags a resolution turn with its payload, so the wait after
    // answering a supplement request says so instead of a blank "thinking".
    if (Array.isArray(last.payload?.resolutions)) return '正在记录补充项，继续写这一章…'
    if (session?.plan?.status === 'awaiting_confirmation') {
      return /确认/.test(last.content) ? '正在确认计划，准备生成…' : '正在修改报告计划…'
    }
  }
  return '思考中…'
})

function applySuggestion(text: string) {
  inputValue.value = text
  nextTick(() => {
    autoGrow()
    inputRef.value?.focus()
  })
}

function pickExample(text: string) {
  applySuggestion(text)
}

/* ── slash 菜单 ── */

const slashVisible = ref(false)
const slashQuery = ref('')
const slashStartPos = ref(-1)
const slashActiveIndex = ref(0)
let slashHideTimer: ReturnType<typeof setTimeout> | null = null

const filteredSlashItems = computed<SlashCommandItem[]>(() => {
  const q = slashQuery.value.trim().toLowerCase()
  if (!q) return SLASH_COMMANDS
  return SLASH_COMMANDS.filter(
    (c) => c.title.toLowerCase().includes(q) || c.description.toLowerCase().includes(q),
  )
})

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
  const isSlashAtStart = lastSlash === 0 || (lastSlash > 0 && /\s/.test(before.charAt(lastSlash - 1)))

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
    slashActiveIndex.value = 0
  }
  slashQuery.value = query
  if (slashActiveIndex.value >= filteredSlashItems.value.length) {
    slashActiveIndex.value = Math.max(0, filteredSlashItems.value.length - 1)
  }
}

function pickSlashItem(item: SlashCommandItem) {
  const el = inputRef.value
  if (!el) return
  const caret = el.selectionStart ?? inputValue.value.length
  const start = slashStartPos.value >= 0 ? slashStartPos.value : caret
  const before = inputValue.value.slice(0, start)
  const after = inputValue.value.slice(caret)
  inputValue.value = before + item.template + after
  hideSlashMenu()
  nextTick(() => {
    autoGrow()
    const insertEnd = before.length + item.template.length
    inputRef.value?.focus()
    inputRef.value?.setSelectionRange(insertEnd, insertEnd)
  })
}

function handleComposerBlur() {
  clearSlashHideTimer()
  slashHideTimer = setTimeout(() => hideSlashMenu(), 160)
}

/* ── 附件 ── */

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

function hideUploadMenu() {
  uploadMenuVisible.value = false
  activeUploadKind.value = null
}

function handlePlusBtnBlur() {
  clearUploadMenuHideTimer()
  uploadMenuHideTimer = window.setTimeout(() => hideUploadMenu(), 160)
}

function toggleUploadMenu() {
  if (uploadMenuVisible.value) return hideUploadMenu()
  clearUploadMenuHideTimer()
  uploadMenuVisible.value = true
}

function openUploadForKind(kind: UploadKind) {
  activeUploadKind.value = kind
  uploadMenuVisible.value = false
  nextTick(() => {
    if (!uploadInputRef.value) return
    uploadInputRef.value.accept = ACCEPT_MAP[kind]
    uploadInputRef.value.value = ''
    uploadInputRef.value.click()
  })
}

function detectKindByFilename(name: string): UploadKind {
  const ext = name.toLowerCase()
  return ext.endsWith('.xls') || ext.endsWith('.xlsx') ? 'excel' : 'word'
}

function handleFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  const kind = activeUploadKind.value
  for (let i = 0; i < input.files.length; i += 1) {
    const file = input.files[i]
    const detected = kind ?? detectKindByFilename(file.name)
    const existing = attachments.value.findIndex((a) => a.kind === detected)
    if (existing >= 0) attachments.value.splice(existing, 1)
    attachments.value.push({
      file_id: `local_${Date.now()}_${i}`,
      filename: file.name,
      kind: detected,
      size: file.size,
      file,
    })
  }
  activeUploadKind.value = null
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
  return [...new Set(Object.values(ACCEPT_MAP).flatMap((value) => value.split(',')))].join(',')
}

/* ── 发送 ── */

async function handleSend() {
  const text = inputValue.value.trim()
  if (!text || store.isSending) return
  const sent = await store.sendMessage({
    text,
    templateFile: attachments.value.find((a) => a.kind === 'word')?.file,
    dataFile: attachments.value.find((a) => a.kind === 'excel')?.file,
  })
  if (!sent) return
  inputValue.value = ''
  attachments.value = []
  await nextTick(() => {
    autoGrow()
    scrollToBottom()
  })
}

/** What the resume bar says: how far the run got, and why it stopped. */
const resumeText = computed(() => {
  const session = store.reportSession
  if (!session) return ''
  const done = Object.keys(session.chapter_drafts ?? {}).length
  const total = session.plan?.sections?.length ?? 0
  const progress = total ? `已完成 ${done}/${total} 章` : `已完成 ${done} 章`
  return session.status === 'cancelled'
    ? `生成已停止，${progress}，进度已保留。`
    : `生成中断了，${progress}，进度已保留。`
})

async function handleStop() {
  if (store.isCancelling) return
  await store.cancelGeneration()
  await nextTick(() => scrollToBottom())
}

/** Resume a run that was stopped or that failed, picking up at its last chapter. */
async function handleResume() {
  if (store.isSending) return
  const sent = await store.sendMessage({ text: '继续' })
  if (!sent) return
  await nextTick(() => scrollToBottom())
}

function handleKeydown(event: KeyboardEvent) {
  if (slashVisible.value) {
    const items = filteredSlashItems.value
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (items.length === 0) return
      const step = event.key === 'ArrowDown' ? 1 : items.length - 1
      slashActiveIndex.value = (slashActiveIndex.value + step) % items.length
      return
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault()
      if (items[slashActiveIndex.value]) pickSlashItem(items[slashActiveIndex.value])
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      hideSlashMenu()
      return
    }
  }
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void handleSend()
  }
}

function autoGrow() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 220)}px`
}

function scrollToBottom() {
  const el = messagesContainer.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  // Plan and report cards lay out after the first paint, growing the
  // scroll height; a second pass keeps the newest turn actually in view.
  requestAnimationFrame(() => {
    if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  })
}

onMounted(() => {
  nextTick(() => {
    inputRef.value?.focus()
    scrollToBottom()
  })
})

onUnmounted(() => {
  clearSlashHideTimer()
  clearUploadMenuHideTimer()
})

watch(
  () => store.messages.length,
  () => nextTick(() => scrollToBottom()),
  { flush: 'post' },
)

watch(
  () => store.currentConversationId,
  (id, previous) => {
    // A draft turning into a real thread is this same composer mid-send, not a
    // switch — clearing here would throw away the text if that send then fails.
    if (!previous && id) return
    inputValue.value = ''
    attachments.value = []
    nextTick(() => inputRef.value?.focus())
  },
)
</script>

<template>
  <div class="chat-panel">
    <div v-if="store.error" class="submit-failed-banner" role="alert">
      <span class="submit-failed-text">{{ store.error }}</span>
      <button type="button" class="submit-failed-close" aria-label="关闭提示" @click="store.clearError()">×</button>
    </div>

    <div ref="messagesContainer" class="chat-scroll">
      <div class="chat-inner">
        <div v-if="messages.length === 0" class="welcome">
          <h1 class="welcome-title">智能数据分析助手</h1>
          <p class="welcome-subtitle">上传报告模板和数据，用对话完成规划、修改与生成</p>
          <div class="welcome-chips">
            <button v-for="ex in EXAMPLES" :key="ex" type="button" class="welcome-chip" @click="pickExample(ex)">
              {{ ex }}
            </button>
          </div>
        </div>

        <template v-for="(message, index) in messages" :key="message.message_id">
          <div v-if="message.role === 'user'" class="msg-row is-user">
            <div class="bubble user-bubble">
              <div class="user-text">{{ message.content }}</div>
              <div v-if="message.attachments.length" class="message-attachments">
                <div v-for="file in message.attachments" :key="file.filename" class="message-attachment">
                  <span class="message-attachment-icon">📎</span>
                  <span class="message-attachment-name" :title="file.filename">{{ file.filename }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="msg-row is-assistant">
            <div class="assistant-stack">
              <div v-if="message.kind === 'error'" class="error-card">
                <div class="error-head">
                  <span class="ac-bar error" />
                  <span class="ac-title">执行失败</span>
                </div>
                <div class="ac-body">
                  <div class="ac-error-text">{{ message.content }}</div>
                </div>
              </div>

              <template v-else>
                <div class="answer-bubble">
                  <div class="md-content" v-html="renderMarkdown(message.content)" />
                </div>
                <PlanCard
                  v-if="message.kind === 'plan'"
                  :message="message"
                  :suggestable="isSuggestablePlan(message, index)"
                  @suggest="applySuggestion"
                />
                <ProgressFlow
                  v-else-if="message.kind === 'progress' && isLatestProgress(message, index)"
                  :message="message"
                  :live="liveProgress"
                  :drafts="store.reportSession?.chapter_drafts ?? null"
                  :session-status="store.reportSession?.status"
                />
                <QuestionCard
                  v-else-if="message.kind === 'question'"
                  :message="message"
                  :pending-ids="pendingQuestionIds"
                  :resolved="resolvedQuestions"
                  :submitting="store.isSending || submittedQuestions.has(message.message_id)"
                  @submit="(items) => submitResolutions(message.message_id, items)"
                />
                <ReportCard v-else-if="message.kind === 'report'" :message="message" />
              </template>
            </div>
          </div>
        </template>

        <div v-if="store.isAwaitingAssistant" class="msg-row is-assistant">
          <div class="assistant-stack">
            <div class="answer-bubble thinking-bubble">
              <span class="loading-dots"><span /><span /><span /></span>
              <span class="thinking-label">{{ thinkingLabel }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="composer" style="position: relative;">
      <div v-if="store.isResumable" class="resume-bar">
        <span class="resume-text">{{ resumeText }}</span>
        <button type="button" class="resume-btn" :disabled="store.isSending" @click="handleResume">
          继续生成
        </button>
      </div>
      <SlashCommandMenu
        v-if="slashVisible"
        :items="filteredSlashItems"
        :active-index="slashActiveIndex"
        @pick="pickSlashItem"
      />
      <div v-if="uploadMenuVisible" class="upload-menu">
        <button type="button" class="upload-menu-item" @click="openUploadForKind('word')">
          <span class="upload-menu-icon word">W</span>
          <div class="upload-menu-meta">
            <div class="upload-menu-title">上传报告模板</div>
            <div class="upload-menu-desc">.docx / .md / .txt</div>
          </div>
        </button>
        <button type="button" class="upload-menu-item" @click="openUploadForKind('excel')">
          <span class="upload-menu-icon excel">X</span>
          <div class="upload-menu-meta">
            <div class="upload-menu-title">上传 Excel 表格</div>
            <div class="upload-menu-desc">.xlsx</div>
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
          aria-label="添加附件"
          title="添加附件"
          @click="toggleUploadMenu"
          @focus="clearUploadMenuHideTimer()"
          @blur="handlePlusBtnBlur"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
        <div class="composer-input-wrap">
          <div v-if="attachments.length > 0" class="attachment-chips">
            <div v-for="a in attachments" :key="a.file_id" class="attachment-chip">
              <span class="attachment-icon" :class="a.kind">{{ a.kind === 'word' ? 'W' : 'X' }}</span>
              <div class="attachment-meta">
                <span class="attachment-name" :title="a.filename">{{ a.filename }}</span>
                <span class="attachment-size">{{ formatFileSize(a.size) }} · {{ KIND_LABEL[a.kind] }}</span>
              </div>
              <button type="button" class="attachment-remove" aria-label="移除附件" @click.stop="removeAttachment(a.file_id)">
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
            placeholder="描述需求、修改计划，或直接确认开始生成"
            rows="1"
            @keydown="handleKeydown"
            @input="handleInputChange(); autoGrow()"
            @focus="clearSlashHideTimer()"
            @blur="handleComposerBlur"
          />
        </div>
        <button
          v-if="store.isGenerating"
          class="send-btn is-stop"
          :disabled="store.isCancelling"
          title="停止生成，已写完的章节会保留"
          @click="handleStop"
        >
          <span v-if="store.isCancelling" class="spinner-small" />
          <template v-else><span class="stop-glyph" />停止</template>
        </button>
        <button v-else class="send-btn" :disabled="store.isSending || !inputValue.trim()" @click="handleSend">
          <span v-if="store.isSending" class="spinner-small" />
          <span v-else>发送</span>
        </button>
      </div>
    </div>
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

.msg-row {
  display: flex;
}

.msg-row.is-user {
  justify-content: flex-end;
}

.msg-row.is-assistant {
  justify-content: flex-start;
}

/* The assistant column is a fixed width, not a shrink-to-fit one.
 *
 * Left to the flex default (`flex: 0 1 auto`) this box is as wide as whatever
 * it happens to hold, so a question card jumped between widths as the user
 * moved through it — narrow with three buttons on screen, stretched once the
 * SQL editor showed a wide result table, narrow again once submitted. Every
 * card in here is a panel, and a panel that resizes while being filled in
 * reads as a glitch. */
.assistant-stack {
  flex: 1 1 auto;
  width: 100%;
  /* Without this a wide child (a preview table with nowrap cells) can still
     push the column past the conversation's width instead of scrolling
     inside its own box. */
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.bubble {
  max-width: 78%;
  padding: 12px 16px;
  border-radius: 18px;
  font-size: 14px;
  line-height: 1.6;
}

.user-bubble {
  background: var(--color-bubble-user-bg);
  color: var(--color-text-dark);
  white-space: pre-wrap;
}

.user-text {
  white-space: pre-wrap;
}

.message-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--color-bubble-user-border);
}

.message-attachment {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 220px;
  padding: 5px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
  color: var(--color-text-dark);
  font-size: 12px;
}

.message-attachment-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.report-final-label { color: var(--color-success); font-weight: 700; font-size: 13px; }

.report-inline h2 { margin: 0 0 12px; font-size: 20px; color: var(--color-text-dark); }

.report-inline h3 { margin: 0 0 10px; font-size: 16px; color: var(--color-text-dark); }

.report-inline-summary { padding: 11px 13px; border-radius: 8px; background: #fff9ef; border-left: 3px solid #f5c76a; margin-bottom: 16px; }

.report-inline-section { margin-top: 16px; }

.report-inline-section h3 { margin: 0 0 7px; font-size: 16px; color: var(--color-text-dark); }

.answer-bubble {
  max-width: 100%;
  background: transparent;
  color: var(--color-text-dark);
}

.answer-bubble.answer-empty {
  padding: 12px 16px;
  color: var(--color-text-light);
}

.error-head {
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

.thinking-bubble {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.thinking-label {
  font-size: 13px;
  color: var(--color-text-medium);
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

.ac-error-text {
  font-size: 13px;
  color: var(--color-error, #dc2626);
  line-height: 1.5;
  padding: 4px 0;
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

.resume-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 9px 12px 9px 14px;
  border: 1px solid var(--border-1, rgba(0, 0, 0, 0.1));
  border-radius: var(--radius-md, 10px);
  background: var(--surface-2, #f7f7f9);
}

.resume-text {
  font-size: 13px;
  color: var(--text-2, #5b5b66);
}

.resume-btn {
  flex-shrink: 0;
  padding: 6px 14px;
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--gradient-primary);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.resume-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.send-btn.is-stop {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: var(--surface-2, #f1f1f4);
  color: var(--text-1, #1f1f22);
  box-shadow: inset 0 0 0 1px var(--border-1, rgba(0, 0, 0, 0.12));
}

.send-btn.is-stop:hover:not(:disabled) {
  background: var(--surface-3, #e8e8ec);
  box-shadow: inset 0 0 0 1px var(--border-2, rgba(0, 0, 0, 0.2));
}

.stop-glyph {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: currentColor;
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
