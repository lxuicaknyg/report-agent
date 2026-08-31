<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useReportStore } from '../../stores/report'
import type { AnswerReportQuestionRequest, ChapterDraft, UserQuestion, ReportArtifact } from '../../types'
import { reportApi } from '../../services/api/reports'
import { renderMarkdown } from '../../utils/markdown'
import { downloadBlob, suggestFilename } from '../../utils/download'

const route = useRoute()
const store = useReportStore()

const sessionId = computed(() => String(route.params.sessionId || ''))

const answerPayload = ref<Record<string, string>>({})
const answeringQuestionId = ref<string | null>(null)
const reportCollapsed = ref(false)

function toggleReport() {
  reportCollapsed.value = !reportCollapsed.value
}

const assembledChapterCount = computed(() =>
  store.currentSession?.assembled_report?.chapters?.length ?? 0,
)

const statusTextMap: Record<string, { label: string; cls: string }> = {
  created:      { label: '已创建', cls: 'status-created' },
  running:      { label: '执行中', cls: 'status-running' },
  waiting_user: { label: '等待补充信息', cls: 'status-waiting' },
  completed:    { label: '已完成', cls: 'status-completed' },
  failed:       { label: '失败',   cls: 'status-failed' },
  cancelled:    { label: '已取消', cls: 'status-cancelled' },
}

const statusBadge = computed(() => {
  if (!store.currentSession) return { label: '加载中', cls: '' }
  return statusTextMap[store.currentSession.status] ?? { label: store.currentSession.status, cls: '' }
})

const isCompleted = computed(() => store.currentSession?.status === 'completed')
const reportTitleForExport = computed(() => {
  return store.currentSession?.title
    || store.currentSession?.template_snapshot?.title
    || '报告'
})

const chapters = computed<ChapterDraft[]>(() => {
  if (!store.currentSession?.chapter_drafts) return []
  const drafts = Object.values(store.currentSession.chapter_drafts) as ChapterDraft[]
  return drafts.sort((a, b) => {
    const orderA = store.currentSession?.plan?.assembly_order?.indexOf(a.section_id) ?? 0
    const orderB = store.currentSession?.plan?.assembly_order?.indexOf(b.section_id) ?? 0
    return orderA - orderB
  })
})

async function submitAnswer(q: UserQuestion) {
  const ans = (answerPayload.value[q.question_id] || '').trim()
  if (!ans) return
  answeringQuestionId.value = q.question_id
  try {
    const req: AnswerReportQuestionRequest = {
      question_id: q.question_id,
      answer: ans,
      auto_resume: true,
    }
    await store.answerQuestion(sessionId.value, req)
  } finally {
    answeringQuestionId.value = null
  }
}

async function downloadArtifact(a: ReportArtifact) {
  const res = await reportApi.downloadArtifact(sessionId.value, a.artifact_id)
  if (res.success && res.data) {
    downloadBlob(res.data, a.name)
  } else if (res.error) {
    alert(`下载失败：${res.error.message}`)
  }
}

function exportDisabledHint(format: 'pdf' | 'docx'): string {
  return `导出 ${format.toUpperCase()} 功能待后端接口就绪后启用`
}

const chaptersCollapsed = ref(true)

function toggleChapters() {
  chaptersCollapsed.value = !chaptersCollapsed.value
}

const expandedChapterIds = ref<Set<string>>(new Set())

function toggleExpand(chapterId: string) {
  if (expandedChapterIds.value.has(chapterId)) {
    expandedChapterIds.value.delete(chapterId)
  } else {
    expandedChapterIds.value.add(chapterId)
  }
}

onMounted(() => {
  void store.reloadSession(sessionId.value)
})

onUnmounted(() => {
  store.stopPolling()
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <div class="crumbs">报告任务 / {{ sessionId }}</div>
        <h2 class="page-title">{{ store.currentSession?.title || store.currentSession?.template_snapshot?.title || '未命名报告' }}</h2>
        <p class="page-desc">{{ store.currentSession?.instruction }}</p>
      </div>
      <div class="head-right">
        <span class="status-chip" :class="statusBadge.cls">{{ statusBadge.label }}</span>
      </div>
    </header>

    <div v-if="store.error" class="error-banner page-banner">
      <span>{{ store.error }}</span>
      <button type="button" class="banner-close" @click="store.clearError()" aria-label="关闭">×</button>
    </div>
    <div v-if="store.pollError" class="warn-banner page-banner">
      <span>{{ store.pollError }}</span>
      <button type="button" class="banner-close" @click="store.clearPollError()" aria-label="关闭">×</button>
    </div>

    <section v-if="store.currentSession?.status === 'waiting_user' && store.currentSession.pending_questions?.length" class="card waiting-card">
      <h3 class="card-title warn">需要你补充以下信息（共 {{ store.currentSession.pending_questions.length }} 条）</h3>
      <div class="q-list">
        <div v-for="q in store.currentSession.pending_questions" :key="q.question_id" class="q-item">
          <div class="q-head">
            <div class="q-content">{{ q.content }}</div>
            <div v-if="q.reason" class="q-reason">原因：{{ q.reason }}</div>
          </div>
          <textarea
            v-model="answerPayload[q.question_id]"
            rows="3"
            class="text-input"
            placeholder="请输入你的回答…"
            :disabled="!!q.answer || answeringQuestionId === q.question_id"
          />
          <div v-if="!q.answer" class="q-actions">
            <button
              type="button"
              class="primary-btn"
              :disabled="!(answerPayload[q.question_id] || '').trim() || answeringQuestionId !== null"
              @click="submitAnswer(q)"
            >
              {{ answeringQuestionId === q.question_id ? '提交中…' : '提交并继续' }}
            </button>
          </div>
          <div v-else class="q-answer">
            你的回答：<span class="q-answer-text">{{ q.answer }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-head-row">
        <h3 class="card-title">章节进度（{{ chapters.filter(c => c.completed).length }} / {{ chapters.length || store.currentSession?.plan?.sections?.length || 0 }}）</h3>
        <button
          type="button"
          class="toggle-expand-btn"
          @click="toggleChapters()"
        >
          {{ chaptersCollapsed ? '展开章节' : '收起章节' }}
        </button>
      </div>
      <template v-if="!chaptersCollapsed">
        <div v-if="store.loadingSession" class="hint">加载中…</div>
        <div v-else-if="chapters.length === 0" class="hint small">
          章节 Writer 使用 Stub 占位，若后端未进入 running 状态可观察 current_step 变化：
          <span class="mono">{{ store.currentSession?.current_step || '—' }}</span>
        </div>
        <ul v-else class="chapter-list">
          <li v-for="c in chapters" :key="c.chapter_id" class="chapter-row">
            <div class="chapter-status" :class="c.completed ? 'done' : 'run'">{{ c.completed ? '完成' : '执行中' }}</div>
            <div class="chapter-body">
              <div class="chapter-head-row">
                <div class="chapter-title">{{ c.title }}</div>
                <button
                  v-if="c.content && c.content.length > 200"
                  type="button"
                  class="toggle-expand-btn"
                  @click="toggleExpand(c.chapter_id)"
                >
                  {{ expandedChapterIds.has(c.chapter_id) ? '收起预览' : '查看全文' }}
                </button>
              </div>
              <div
                v-if="c.content"
                class="chapter-preview md-content"
                v-html="renderMarkdown(expandedChapterIds.has(c.chapter_id) ? c.content : (c.content.length > 200 ? c.content.slice(0, 200) + '…' : c.content))"
              />
              <div v-if="c.questions?.length" class="chapter-qcount">本章节追问 {{ c.questions.filter((q: UserQuestion) => !q.answer).length }} 条待答</div>
            </div>
          </li>
        </ul>
      </template>
      <div v-else class="collapsed-hint">
        共 {{ chapters.length || store.currentSession?.plan?.sections?.length || 0 }} 章，已完成 {{ chapters.filter(c => c.completed).length }} 章。点击右上角「展开章节」查看详情
      </div>
    </section>

    <section v-if="store.currentSession?.assembled_report" class="card">
      <div class="card-head-row">
        <h3 class="card-title">组装报告</h3>
        <div class="report-head-actions">
          <div class="export-row">
            <button
              type="button"
              class="secondary-btn"
              disabled
              :title="exportDisabledHint('pdf')"
            >
              导出 PDF
            </button>
            <button
              type="button"
              class="secondary-btn"
              disabled
              :title="exportDisabledHint('docx')"
            >
              导出 Word
            </button>
            <span v-if="!isCompleted" class="muted small">
              仅在「已完成」状态且接口上线后可导出
            </span>
            <span v-else class="muted small">{{ suggestFilename(reportTitleForExport, 'pdf') }}</span>
          </div>
          <button
            type="button"
            class="toggle-expand-btn"
            @click="toggleReport()"
          >
            {{ reportCollapsed ? '展开报告' : '收起报告' }}
          </button>
        </div>
      </div>
      <template v-if="!reportCollapsed">
        <article class="report-preview md-content">
          <h1 class="report-head">{{ store.currentSession.assembled_report.title }}</h1>
          <section v-if="store.currentSession.assembled_report.executive_summary" class="report-section summary">
            <h2 class="summary-h">摘要</h2>
            <div
              class="summary-text"
              v-html="renderMarkdown(store.currentSession.assembled_report.executive_summary)"
            />
          </section>
          <section v-for="c in store.currentSession.assembled_report.chapters" :key="c.chapter_id" class="report-section">
            <h2 class="chapter-h">{{ c.title }}</h2>
            <div class="chapter-md" v-html="renderMarkdown(c.content)" />
          </section>
        </article>
      </template>
      <div v-else class="collapsed-hint">
        共 {{ assembledChapterCount }} 章，
        <span v-if="store.currentSession.assembled_report.executive_summary">含摘要，</span>
        点击右上角「展开报告」查看全文
      </div>
    </section>

    <section v-if="store.currentSession?.artifacts?.length" class="card">
      <h3 class="card-title">产物下载</h3>
      <ul class="artifact-list">
        <li v-for="a in store.currentSession.artifacts" :key="a.artifact_id" class="artifact-row">
          <div class="artifact-body">
            <div class="artifact-name">{{ a.name }}</div>
            <div class="artifact-meta">
              <span class="tag format">{{ a.format }}</span>
              <span>{{ new Date(a.created_at).toLocaleString() }}</span>
            </div>
          </div>
          <button type="button" class="secondary-btn" @click="downloadArtifact(a)">下载</button>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }

.crumbs { font-size: 12px; color: var(--color-text-light); margin-bottom: 6px; font-family: 'JetBrains Mono', Consolas, monospace; }

.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 4px; }

.page-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
}
.error-banner {
  background: #fde8e8;
  border: 1px solid #f5b7b7;
  color: #b91c1c;
}
.warn-banner {
  background: #fff6e6;
  border: 1px solid #f5c76a;
  color: #8a5a00;
}
.banner-close {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 0;
  background: transparent;
  color: inherit;
  opacity: 0.7;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.banner-close:hover { opacity: 1; background: rgba(0,0,0,0.05); }

.card-head-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }
.report-head-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.export-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }
.page-desc { font-size: 13px; color: var(--color-text-medium); margin: 0; max-width: 70ch; }

.head-right { display: flex; align-items: center; }

.muted { color: var(--color-text-medium); }
.small { font-size: 12px; }

.status-chip {
  display: inline-flex; align-items: center;
  padding: 5px 13px; border-radius: 999px; font-size: 12px; font-weight: 600;
}
.status-created     { background: #f3f4f6; color: #475569; }
.status-running     { background: var(--color-primary-light); color: var(--color-primary); animation: pulse 1.6s infinite; }
.status-waiting     { background: #fff6e6; color: #c77a00; }
.status-completed   { background: #e6f6ec; color: #157a42; }
.status-failed      { background: #fde8e8; color: #b91c1c; }
.status-cancelled   { background: #f3f4f6; color: #6b7280; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .65; } }

.card { background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }
.card-title { font-size: 15px; font-weight: 600; margin: 0; color: var(--color-text-dark); }
.card-title.warn { color: #c77a00; }
.collapsed-hint {
  padding: 10px 14px;
  background: #fbfaff;
  border-radius: 8px;
  font-size: 13px;
  color: var(--color-text-medium);
}

.hint { padding: 24px; text-align: center; color: var(--color-text-medium); font-size: 13.5px; }
.hint.small { padding: 16px; font-size: 13px; text-align: left; background: #fbfaff; border-radius: 10px; }

.mono { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12.5px; padding: 2px 6px; background: #f5f3fa; border-radius: 4px; color: #4b3f66; }

.waiting-card { border-color: #f5c76a; background: #fffbf0; }

.q-list { display: flex; flex-direction: column; gap: 14px; }
.q-item { background: #fff; border: 1px solid var(--color-primary-border); border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.q-content { font-size: 14px; color: var(--color-text-dark); font-weight: 500; }
.q-reason { font-size: 12.5px; color: var(--color-text-medium); margin-top: 4px; }
.q-actions { display: flex; justify-content: flex-end; }
.q-answer { font-size: 13px; color: var(--color-text-medium); }
.q-answer-text { color: var(--color-primary); font-weight: 500; }

.text-input {
  padding: 9px 12px; border: 1px solid var(--color-primary-border); border-radius: 8px;
  font-size: 13.5px; font-family: inherit; background: #fff; width: 100%; line-height: 1.55;
}

.chapter-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
.chapter-row { display: flex; gap: 12px; padding: 10px 12px; background: #fdfcff; border: 1px solid var(--color-primary-border); border-radius: 10px; }
.chapter-status {
  width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700;
}
.chapter-status.done { background: #e6f6ec; color: #157a42; }
.chapter-status.run { background: var(--color-primary-light); color: var(--color-primary); }
.chapter-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.chapter-head-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.chapter-title { font-size: 14px; font-weight: 600; color: var(--color-text-dark); }
.toggle-expand-btn {
  flex-shrink: 0;
  padding: 3px 10px;
  border: 1px solid var(--color-primary-border);
  background: #fff;
  color: var(--color-primary);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
}
.toggle-expand-btn:hover { background: var(--color-primary-light); }
.chapter-preview {
  margin: 2px 0 0; padding: 10px 12px; background: #f7f5fc; border-radius: 8px;
  font-size: 12.5px; line-height: 1.65; color: #4b3f66;
}
.chapter-qcount { font-size: 12px; color: #c77a00; }

.report-preview {
  border: 1px solid var(--color-primary-border);
  border-radius: 10px;
  padding: 22px 24px;
  background: #fffdfc;
}
.report-head { font-size: 22px; font-weight: 700; margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--color-border); color: var(--color-text-dark); }
.report-section { margin: 14px 0; }
.summary-h { font-size: 17px; font-weight: 600; margin: 0 0 8px; color: var(--color-text-dark); }
.chapter-h { font-size: 17px; font-weight: 600; margin: 0 0 8px; color: var(--color-text-dark); }
.summary-text, .chapter-md {
  font-size: 14px; line-height: 1.75; color: var(--color-text-dark);
}
.report-section.summary .summary-text {
  background: #fff9ef; padding: 12px 14px; border-radius: 8px; border-left: 3px solid #f5c76a;
}

.md-content :deep(.md-h) { font-weight: 700; color: var(--color-text-dark); margin: 0.8em 0 0.4em; line-height: 1.35; }
.md-content :deep(.md-h1) { font-size: 22px; }
.md-content :deep(.md-h2) { font-size: 18px; }
.md-content :deep(.md-h3) { font-size: 15.5px; }
.md-content :deep(.md-h4), .md-content :deep(.md-h5), .md-content :deep(.md-h6) { font-size: 14px; }

.md-content :deep(.md-p) { margin: 0 0 10px; }

.md-content :deep(.md-ul), .md-content :deep(.md-ol) { padding-left: 22px; margin: 0 0 10px; }
.md-content :deep(.md-ul) { list-style: disc; }
.md-content :deep(.md-ol) { list-style: decimal; }
.md-content :deep(.md-li) { margin: 2px 0; line-height: 1.7; }

.md-content :deep(.md-strong) { font-weight: 700; color: var(--color-text-dark); }
.md-content :deep(.md-em) { font-style: italic; }

.md-content :deep(.md-inline-code) {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 0.92em;
  background: #f5f3fa;
  color: #4b3f66;
  padding: 1px 6px;
  border-radius: 4px;
}

.md-content :deep(.md-link) { color: var(--color-primary); text-decoration: underline; }

.artifact-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.artifact-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border: 1px solid var(--color-primary-border); border-radius: 10px;
}
.artifact-body { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.artifact-name { font-size: 14px; font-weight: 600; color: var(--color-text-dark); }
.artifact-meta { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--color-text-medium); }

.tag.format { display: inline-block; padding: 2px 9px; border-radius: 999px; background: #eef5ff; color: #2563eb; font-size: 11px; font-weight: 600; }

.primary-btn, .secondary-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 16px; border-radius: 9px; font-size: 13px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}
.primary-btn { border: 0; background: var(--gradient-primary); color: #fff; }
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.secondary-btn { border: 1px solid var(--color-primary-border); background: #fff; color: var(--color-primary); }
.secondary-btn:hover { background: var(--color-primary-light); }
</style>
