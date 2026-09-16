<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useReportStore } from '../../stores/report'
import type { ChapterDraft, ReportArtifact } from '../../types'
import { reportApi } from '../../services/api/reports'
import { renderMarkdown } from '../../utils/markdown'
import { downloadBlob } from '../../utils/download'

/**
 * Read-only view of one report. Every change to a report — plan revisions,
 * answers, approval — happens in its conversation, so this page renders and
 * downloads, and never edits.
 */
const route = useRoute()
const store = useReportStore()

const sessionId = computed(() => String(route.params.sessionId || ''))

const statusTextMap: Record<string, { label: string; cls: string }> = {
  created:      { label: '已创建', cls: 'status-created' },
  awaiting_confirmation: { label: '待确认计划', cls: 'status-waiting' },
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

const plan = computed(() => store.currentSession?.plan ?? null)
const planDimensions = computed(() => Object.entries(plan.value?.global_context?.dimensions || {}))

const chapters = computed<ChapterDraft[]>(() => {
  if (!store.currentSession?.chapter_drafts) return []
  const drafts = Object.values(store.currentSession.chapter_drafts) as ChapterDraft[]
  const order = store.currentSession.plan?.assembly_order ?? []
  return drafts.sort((a, b) => order.indexOf(a.section_id) - order.indexOf(b.section_id))
})

async function downloadArtifact(a: ReportArtifact) {
  const res = await reportApi.downloadArtifact(sessionId.value, a.artifact_id)
  if (res.success && res.data) downloadBlob(res.data, a.name)
  else if (res.error) alert(`下载失败：${res.error.message}`)
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
        <div class="crumbs">报告会话 / {{ sessionId }}</div>
        <h2 class="page-title">{{ store.currentSession?.title || store.currentSession?.template_snapshot?.title || '未命名报告' }}</h2>
        <p class="page-desc">{{ store.currentSession?.instruction }}</p>
      </div>
      <div class="head-right">
        <span class="status-chip" :class="statusBadge.cls">{{ statusBadge.label }}</span>
      </div>
    </header>

    <section v-if="plan" class="card">
      <div class="plan-head">
        <div>
          <h3 class="card-title">报告计划</h3>
          <p class="plan-desc">计划在对话中修改与确认，本页只读展示当前版本。</p>
        </div>
        <span class="plan-version">v{{ plan.version }}</span>
      </div>
      <div class="plan-context">
        <div class="plan-field">
          <span class="plan-field-label">报告期间</span>
          <span class="plan-field-value">{{ plan.global_context?.report_period || '未指定' }}</span>
        </div>
        <div v-for="[key, value] in planDimensions" :key="key" class="plan-field">
          <span class="plan-field-label">{{ key }}</span>
          <span class="plan-field-value">{{ value }}</span>
        </div>
      </div>
      <ol class="plan-chapters">
        <li v-for="chapter in plan.chapters || []" :key="chapter.section_id" class="plan-chapter">
          <div class="plan-chapter-title">{{ chapter.title }}</div>
          <div v-if="chapter.metrics.length" class="plan-metrics">
            <span v-for="metric in chapter.metrics" :key="metric" class="plan-metric">{{ metric }}</span>
          </div>
          <ul v-if="chapter.subsections?.length" class="plan-subsections">
            <li
              v-for="sub in chapter.subsections"
              :key="sub.section_id"
              class="plan-subsection"
              :style="{ paddingLeft: `${Math.max(0, sub.level - chapter.level - 1) * 14}px` }"
            >{{ sub.title }}</li>
          </ul>
        </li>
      </ol>
    </section>

    <section class="card">
      <h3 class="card-title">章节进度（{{ chapters.filter(c => c.completed).length }} / {{ plan?.chapters?.length ?? 0 }}）</h3>
      <div v-if="store.loadingSession && chapters.length === 0" class="hint">加载中…</div>
      <div v-else-if="chapters.length === 0" class="hint small">
        暂无已完成章节，当前步骤：<span class="mono">{{ store.currentSession?.current_step || '—' }}</span>
      </div>
      <ul v-else class="chapter-list">
        <li v-for="c in chapters" :key="c.chapter_id" class="chapter-row">
          <div class="chapter-status" :class="c.completed ? 'done' : 'run'">{{ c.completed ? '完成' : '执行中' }}</div>
          <div class="chapter-body">
            <div class="chapter-title">{{ c.title }}</div>
            <div
              v-if="c.content"
              class="chapter-preview md-content"
              v-html="renderMarkdown(c.content.length > 200 ? c.content.slice(0, 200) + '…' : c.content)"
            />
          </div>
        </li>
      </ul>
    </section>

    <section v-if="store.currentSession?.assembled_report" class="card">
      <h3 class="card-title">报告全文</h3>
      <article class="report-preview md-content">
        <h1 class="report-head">{{ store.currentSession.assembled_report.title }}</h1>
        <section v-if="store.currentSession.assembled_report.executive_summary" class="report-section summary">
          <h2 class="summary-h">摘要</h2>
          <div class="summary-text" v-html="renderMarkdown(store.currentSession.assembled_report.executive_summary)" />
        </section>
        <section v-for="c in store.currentSession.assembled_report.chapters" :key="c.chapter_id" class="report-section">
          <h2 class="chapter-h">{{ c.title }}</h2>
          <div class="chapter-md" v-html="renderMarkdown(c.content)" />
        </section>
      </article>
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
.page {display: flex; flex-direction: column; gap: 18px; }

.crumbs {font-size: 12px; color: var(--color-text-light); margin-bottom: 6px; font-family: 'JetBrains Mono', Consolas, monospace; }

.page-head {display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }

.page-title {font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }

.page-desc {font-size: 13px; color: var(--color-text-medium); margin: 0; max-width: 70ch; }

.head-right {display: flex; align-items: center; }

.status-chip {display: inline-flex; align-items: center;
  padding: 5px 13px; border-radius: 999px; font-size: 12px; font-weight: 600;
}

.status-created {background: #f3f4f6; color: #475569; }

.status-running {background: var(--color-primary-light); color: var(--color-primary); animation: pulse 1.6s infinite; }

.status-waiting {background: #fff6e6; color: #c77a00; }

.status-completed {background: #e6f6ec; color: #157a42; }

.status-failed {background: #fde8e8; color: #b91c1c; }

.status-cancelled {background: #f3f4f6; color: #6b7280; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .65; } }

.card {background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }

.card-title {font-size: 15px; font-weight: 600; margin: 0 0 14px; color: var(--color-text-dark); }

.card-title.warn {color: #c77a00; }

.hint {padding: 24px; text-align: center; color: var(--color-text-medium); font-size: 13.5px; }

.hint.small {padding: 16px; font-size: 13px; text-align: left; background: #fbfaff; border-radius: 10px; }

.mono {font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12.5px; padding: 2px 6px; background: #f5f3fa; border-radius: 4px; color: #4b3f66; }

.plan-head {display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }

.plan-desc {margin: -8px 0 14px; color: var(--color-text-medium); font-size: 12.5px; }

.plan-version {color: var(--color-primary); background: var(--color-primary-light); border-radius: 999px; padding: 4px 9px; font-size: 12px; }

.plan-chapters {display: flex; flex-direction: column; gap: 8px; }

.plan-chapter {display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--color-primary-border); border-radius: 9px; background: #fff; }

.chapter-list {list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }

.chapter-row {display: flex; gap: 12px; padding: 10px 12px; background: #fdfcff; border: 1px solid var(--color-primary-border); border-radius: 10px; }

.chapter-status {width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700;
}

.chapter-status.done {background: #e6f6ec; color: #157a42; }

.chapter-status.run {background: var(--color-primary-light); color: var(--color-primary); }

.chapter-body {flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }

.chapter-title {font-size: 14px; font-weight: 600; color: var(--color-text-dark); }

.chapter-preview {margin: 2px 0 0; padding: 10px 12px; background: #f7f5fc; border-radius: 8px;
  font-size: 12.5px; line-height: 1.65; color: #4b3f66;
}

.report-preview {border: 1px solid var(--color-primary-border);
  border-radius: 10px;
  padding: 22px 24px;
  background: #fffdfc;
}

.report-head {font-size: 22px; font-weight: 700; margin: 0 0 16px; padding-bottom: 10px; border-bottom: 1px solid var(--color-border); color: var(--color-text-dark); }

.report-section {margin: 14px 0; }

.summary-h {font-size: 17px; font-weight: 600; margin: 0 0 8px; color: var(--color-text-dark); }

.chapter-h {font-size: 17px; font-weight: 600; margin: 0 0 8px; color: var(--color-text-dark); }

.summary-text, .chapter-md {font-size: 14px; line-height: 1.75; color: var(--color-text-dark);
}

.report-section.summary .summary-text {background: #fff9ef; padding: 12px 14px; border-radius: 8px; border-left: 3px solid #f5c76a;
}

.artifact-list {list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }

.artifact-row {display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border: 1px solid var(--color-primary-border); border-radius: 10px;
}

.artifact-body {display: flex; flex-direction: column; gap: 3px; min-width: 0; }

.artifact-name {font-size: 14px; font-weight: 600; color: var(--color-text-dark); }

.artifact-meta {display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--color-text-medium); }

.tag.format {display: inline-block; padding: 2px 9px; border-radius: 999px; background: #eef5ff; color: #2563eb; font-size: 11px; font-weight: 600; }

.secondary-btn {display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 16px; border-radius: 9px; font-size: 13px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}

.secondary-btn {border: 1px solid var(--color-primary-border); background: #fff; color: var(--color-primary); }

.secondary-btn:hover {background: var(--color-primary-light); }

.plan-context { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.plan-field {
  display: flex; align-items: center; gap: 6px;
  background: #fbfaff; border-radius: 8px; padding: 4px 10px; font-size: 12px;
}
.plan-field-label { color: var(--color-text-light); }
.plan-field-value { color: var(--color-text-dark); font-weight: 500; }

.plan-chapter-title { font-size: 13.5px; font-weight: 600; color: var(--color-text-dark); }
.plan-metrics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.plan-metric {
  font-size: 11.5px; padding: 2px 8px; border-radius: 6px;
  background: var(--color-primary-light); color: var(--color-primary);
}

.plan-subsections {
  list-style: none;
  margin: 8px 0 0;
  padding: 0 0 0 10px;
  border-left: 2px solid var(--color-primary-border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plan-subsection { font-size: 12.5px; color: var(--color-text-medium); line-height: 1.5; }
</style>
