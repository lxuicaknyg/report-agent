<script setup lang="ts">
import { computed, nextTick, reactive } from 'vue'
import PastedTableEditor from './PastedTableEditor.vue'
import SqlSupplementEditor from './SqlSupplementEditor.vue'
import { useConnectionStore } from '../../../stores/connection'
import type {
  AnalysisType,
  ConnectionQueryResult,
  ParsedTable,
  SupplementShape,
  Message,
  QuestionResolutionInput,
  QuestionMessagePayload,
  UserQuestion,
} from '../../../types'

const props = defineProps<{
  message: Message
  /** Questions still open on the live session; absent once the chapter moved on. */
  pendingIds?: string[] | null
  resolved?: Record<string, UserQuestion> | null
  submitting?: boolean
}>()
const emit = defineEmits<{ (e: 'submit', resolutions: QuestionResolutionInput[]): void }>()

const connections = useConnectionStore()

/** The backend stores the value verbatim and hands it to the chapter writer, so
 * these caps are about keeping a metric a metric — not a backend constraint. */
const VALUE_MAX = 120
const NOTE_MAX = 200

const chapters = computed(
  () => (props.message.payload as unknown as QuestionMessagePayload).chapters ?? [],
)
const questions = computed(() => chapters.value.flatMap((chapter) => chapter.questions))

/** Read-only once none of these questions are open any more. */
const isOpen = computed(() => {
  const pending = props.pendingIds
  if (!pending) return false
  return questions.value.some((q) => pending.includes(q.question_id))
})

/** What the chapter is missing, decided when the question was raised. It is
 * what selects the ways of answering below — the user is never asked to
 * classify their own answer. */
const EXPECT_LABEL: Record<string, string> = {
  value: '需要一个数值',
  table: '需要一份明细清单',
  text: '需要一段说明',
}

const EXPECT_PLACEHOLDER: Record<string, string> = {
  value: '例如：42,060,000 元、12.5%、1.8 亿',
  text: '例如：本期口径为含贴现的绿色信贷余额',
}

/** True for a question the chapter will print as rows rather than in a
 * sentence. */
function wantsTable(question: UserQuestion): boolean {
  return question.expected === 'table'
}

type Draft = {
  action: 'value' | 'sql' | 'paste' | 'drop' | null
  value: string
  note: string
  connectionId: string
  query: string
  /** Set on a single-figure question whose query turns out to answer with a
   * list, from the correction offered beside that refusal. */
  asTable: boolean
  /** Rows pasted in, and what the server read them as. */
  text: string
  parsed: ParsedTable | null
  running: boolean
  result: ConnectionQueryResult | null
  /** Which derived analysis is being generated, if any. */
  generating: AnalysisType | null
  /** The SQL a generated query replaced, kept so it can be put back. */
  replaced: string
  generateError: string
  /** Identifies the connection and SQL `result` was produced from, so editing
   * either one invalidates the trial run instead of letting a stale reading be
   * submitted. */
  resultKey: string
}
const drafts = reactive<Record<string, Draft>>({})

function draftFor(question: UserQuestion): Draft {
  if (!drafts[question.question_id]) {
    drafts[question.question_id] = {
      action: null,
      value: '',
      note: '',
      connectionId: '',
      query: '',
      asTable: false,
      text: '',
      parsed: null,
      running: false,
      result: null,
      resultKey: '',
      generating: null,
      replaced: '',
      generateError: '',
    }
  }
  return drafts[question.question_id]
}

/**
 * How this question's query is read: as one figure, or as rows.
 *
 * It comes from the question rather than from anything the user picked —
 * and from their correction, on a question we classified wrongly.
 */
function shapeFor(question: UserQuestion): SupplementShape {
  return wantsTable(question) || draftFor(question).asTable ? 'table' : 'value'
}

/** What a trial run's result belongs to. */
function runKey(question: UserQuestion, draft: Draft): string {
  return `${draft.connectionId}\u0000${shapeFor(question)}\u0000${draft.query.trim()}`
}

/** True while the result on screen still describes what is in the editor. */
function isFresh(question: UserQuestion): boolean {
  const draft = draftFor(question)
  return draft.result !== null && draft.resultKey === runKey(question, draft)
}

/**
 * Rewrite the current query into a year-on-year / period-on-period one.
 *
 * The result only lands in the editor — it is never run here. A generated
 * query is a proposal, and the user has to try it like any other, which also
 * means the previous trial run is invalidated the moment the SQL changes.
 */
async function generateAnalysis(question: UserQuestion, type: AnalysisType) {
  const draft = draftFor(question)
  if (draft.generating || !draft.connectionId || !draft.query.trim()) return
  const previous = draft.query
  draft.generating = type
  draft.generateError = ''
  try {
    const result = await connections.analysisSql(draft.connectionId, previous.trim(), type)
    if (!result.success || !result.generated_sql) {
      draft.generateError = result.message || '生成失败，请稍后重试'
      return
    }
    draft.replaced = previous
    draft.query = result.generated_sql
  } finally {
    draft.generating = null
  }
}

function restoreQuery(question: UserQuestion) {
  const draft = draftFor(question)
  if (!draft.replaced) return
  draft.query = draft.replaced
  draft.replaced = ''
  draft.generateError = ''
}

async function runQuery(question: UserQuestion) {
  const draft = draftFor(question)
  if (draft.running || !draft.connectionId || !draft.query.trim()) return
  const key = runKey(question, draft)
  draft.running = true
  try {
    const result = await connections.query(
      draft.connectionId,
      draft.query.trim(),
      shapeFor(question),
    )
    // The user may have kept typing while this was in flight; label the result
    // with the query it actually ran so a later edit still invalidates it.
    draft.result = result
    draft.resultKey = key
  } finally {
    draft.running = false
  }
}

/**
 * Record this question's answer as a list after all.
 *
 * Raised as a single figure, answered by a query that returns rows — which
 * usually means the metric was always a list and we said otherwise. The query
 * is re-run immediately, because the user clicked this wanting those rows, not
 * wanting to press 试跑 again.
 */
function correctToTable(question: UserQuestion) {
  const draft = draftFor(question)
  if (draft.asTable) return
  draft.asTable = true
  draft.result = null
  draft.resultKey = ''
  void runQuery(question)
}

/**
 * What is wrong with what has been typed so far.
 *
 * An empty field is "not done yet", not an error — the message only appears
 * once there is something to correct, so the card does not scold on arrival.
 */
function errorFor(question: UserQuestion): string {
  const draft = draftFor(question)
  if (draft.action !== 'value') return ''
  const value = draft.value.trim()
  if (!value) return ''
  if (value.length > VALUE_MAX) return `太长了，请控制在 ${VALUE_MAX} 个字以内`
  if (question.expected === 'value' && !/\d/.test(value)) {
    return '这里要的是数值，可以带单位。填不出来就选「不补充，从报告中删除」。'
  }
  if (draft.note.length > NOTE_MAX) return `口径说明请控制在 ${NOTE_MAX} 个字以内`
  return ''
}

function settled(question: UserQuestion): boolean {
  const draft = draftFor(question)
  if (draft.action === 'drop') return true
  if (draft.action === 'sql') {
    // A query must have been run successfully: the data goes into the report,
    // so the user has to have seen it before submitting.
    if (!isFresh(question)) return false
    const found = draft.result?.extraction
    if (!found || found.error) return false
    return shapeFor(question) === 'table' ? found.rows.length > 0 : found.value != null
  }
  if (draft.action === 'paste') {
    // Same rule as a query: the rows on screen are the rows that get
    // submitted, so there have to be rows on screen.
    return draft.parsed !== null && draft.parsed.rows.length > 0
  }
  return draft.action === 'value' && draft.value.trim() !== '' && !errorFor(question)
}

function remainingIn(chapterQuestions: UserQuestion[]): number {
  return chapterQuestions.filter((q) => !settled(q)).length
}

const remaining = computed(() => questions.value.filter((q) => !settled(q)).length)
const settledCount = computed(() => questions.value.length - remaining.value)
const canSubmit = computed(() => remaining.value === 0 && !props.submitting)

function valueInputId(question: UserQuestion): string {
  return `qv-${question.question_id}`
}

function choose(question: UserQuestion, action: Draft['action']) {
  const draft = draftFor(question)
  draft.action = action
  if (action === 'value') {
    nextTick(() => document.getElementById(valueInputId(question))?.focus())
  }
}

function submit() {
  if (!canSubmit.value) return
  emit(
    'submit',
    questions.value.map((question) => {
      const draft = draftFor(question)
      if (draft.action === 'drop') {
        return { question_id: question.question_id, action: 'drop' as const }
      }
      if (draft.action === 'sql') {
        // No value is sent: the backend re-runs the statement and reads the
        // number out of it, so what lands on the report is what the database
        // returned rather than what travelled back through the browser.
        return {
          question_id: question.question_id,
          action: 'sql' as const,
          connection_id: draft.connectionId,
          query: draft.query.trim(),
          ...(draft.asTable ? { as_table: true } : {}),
          ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
        }
      }
      if (draft.action === 'paste') {
        // The text is sent, not the parsed rows: the backend reads it with the
        // same parser the preview came from, so nothing can differ between
        // what was approved and what is recorded.
        return {
          question_id: question.question_id,
          action: 'table' as const,
          text: draft.text,
          ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
        }
      }
      return {
        question_id: question.question_id,
        action: 'value' as const,
        value: draft.value.trim(),
        ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
      }
    }),
  )
}

/** How a question was settled, for the read-only view after submission. */
function outcome(question: UserQuestion): { dropped: boolean; text: string } | null {
  const stored = props.resolved?.[question.question_id]
  if (stored?.resolution === 'dropped') return { dropped: true, text: '已从报告中删除该指标' }
  if (stored?.resolution === 'value') {
    return {
      dropped: false,
      text: stored.note ? `已补充：${stored.value}（${stored.note}）` : `已补充：${stored.value}`,
    }
  }
  if (stored?.resolution === 'sql') {
    const body = stored.value ?? `明细 ${(stored.rows ?? []).length} 行`
    return { dropped: false, text: `已取数：${body}${qualifier(stored)}` }
  }
  if (stored?.resolution === 'table') {
    return {
      dropped: false,
      text: `已补充：明细 ${(stored.rows ?? []).length} 行${qualifier(stored)}`,
    }
  }
  const draft = drafts[question.question_id]
  if (draft?.action === 'drop') return { dropped: true, text: '已从报告中删除该指标' }
  if (draft?.action === 'sql' && draft.result?.extraction) {
    const found = draft.result.extraction
    if (found.value) return { dropped: false, text: `已取数：${found.value}` }
    if (found.rows.length) {
      return { dropped: false, text: `已取数：明细 ${found.rows.length} 行` }
    }
  }
  if (draft?.action === 'paste' && draft.parsed) {
    return { dropped: false, text: `已补充：明细 ${draft.parsed.row_count} 行` }
  }
  if (draft?.action === 'value' && draft.value) {
    return { dropped: false, text: `已补充：${draft.value}` }
  }
  return null
}

/** The dimensions and note a SQL-supplied value was recorded with. */
function qualifier(stored: UserQuestion): string {
  const parts = Object.entries(stored.dimensions ?? {}).map(([name, value]) => `${name}=${value}`)
  if (stored.note) parts.push(stored.note)
  return parts.length ? `（${parts.join('；')}）` : ''
}
</script>

<template>
  <div class="ask" :class="{ 'is-open': isOpen }">
    <div class="ask-head">
      <span class="ask-badge" aria-hidden="true">
        <svg
          viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor"
          stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"
        >
          <path d="M12 9v4" /><path d="M12 17h.01" />
          <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
        </svg>
      </span>
      <div class="ask-head-copy">
        <span class="ask-title">{{ isOpen ? '需要你补充数据才能继续' : '本章的补充项已处理' }}</span>
        <span class="ask-sub">写这一章时有指标取不到数，处理完就接着往下写</span>
      </div>
      <span v-if="isOpen" class="ask-counter">
        已处理 <strong>{{ settledCount }}</strong>/{{ questions.length }}
      </span>
    </div>

    <div v-for="chapter in chapters" :key="chapter.section_id" class="ask-chapter">
      <div class="ask-chapter-head">
        <span class="ask-chapter-title">{{ chapter.title }}</span>
        <span v-if="isOpen && remainingIn(chapter.questions) > 0" class="ask-chapter-left">
          还差 {{ remainingIn(chapter.questions) }} 项
        </span>
      </div>

      <div
        v-for="q in chapter.questions"
        :key="q.question_id"
        class="ask-item"
        :class="{ done: isOpen && settled(q) }"
      >
        <div class="ask-item-head">
          <span class="ask-metric">{{ q.metric || q.content }}</span>
          <span class="ask-expect">{{ EXPECT_LABEL[q.expected || 'text'] || '需要补充' }}</span>
          <svg
            v-if="isOpen && settled(q)"
            class="ask-tick" viewBox="0 0 24 24" width="14" height="14" fill="none"
            stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"
          ><polyline points="20 6 9 17 4 12" /></svg>
        </div>
        <p v-if="q.metric" class="ask-reason">{{ q.content }}</p>

        <template v-if="isOpen">
          <div class="ask-choices" role="group" :aria-label="`如何处理${q.metric || '该指标'}`">
            <button
              v-if="wantsTable(q)"
              type="button"
              class="ask-choice"
              :class="{ active: draftFor(q).action === 'paste' }"
              :aria-pressed="draftFor(q).action === 'paste'"
              @click="choose(q, 'paste')"
            >粘贴明细数据</button>
            <button
              v-else
              type="button"
              class="ask-choice"
              :class="{ active: draftFor(q).action === 'value' }"
              :aria-pressed="draftFor(q).action === 'value'"
              @click="choose(q, 'value')"
            >我来补充</button>
            <button
              type="button"
              class="ask-choice"
              :class="{ active: draftFor(q).action === 'sql' }"
              :aria-pressed="draftFor(q).action === 'sql'"
              @click="choose(q, 'sql')"
            >写 SQL 取数</button>
            <button
              type="button"
              class="ask-choice danger"
              :class="{ active: draftFor(q).action === 'drop' }"
              :aria-pressed="draftFor(q).action === 'drop'"
              @click="choose(q, 'drop')"
            >不补充，从报告中删除</button>
          </div>

          <div v-if="draftFor(q).action === 'value'" class="ask-fields">
            <label class="ask-field">
              <span class="ask-field-label">数值</span>
              <input
                :id="valueInputId(q)"
                v-model="draftFor(q).value"
                class="ask-input"
                :class="{ invalid: !!errorFor(q) }"
                :placeholder="EXPECT_PLACEHOLDER[q.expected || 'text']"
                :maxlength="VALUE_MAX"
                :inputmode="q.expected === 'value' ? 'decimal' : undefined"
                autocomplete="off"
                enterkeyhint="done"
              />
            </label>
            <label class="ask-field note">
              <span class="ask-field-label">口径说明<span class="ask-optional">选填</span></span>
              <input
                v-model="draftFor(q).note"
                class="ask-input"
                placeholder="例如：含贴现；期末余额口径"
                :maxlength="NOTE_MAX"
                autocomplete="off"
              />
            </label>
            <p v-if="errorFor(q)" class="ask-error">{{ errorFor(q) }}</p>
          </div>

          <div v-else-if="draftFor(q).action === 'sql'" class="ask-fields sql-block">
            <SqlSupplementEditor
              :metric="q.metric || q.content"
              :connection-id="draftFor(q).connectionId"
              :query="draftFor(q).query"
              :shape="shapeFor(q)"
              :running="draftFor(q).running"
              :result="draftFor(q).result"
              :fresh="isFresh(q)"
              :generating="draftFor(q).generating"
              :replaced="draftFor(q).replaced"
              :generate-error="draftFor(q).generateError"
              @update:connection-id="draftFor(q).connectionId = $event"
              @update:query="draftFor(q).query = $event"
              @run="runQuery(q)"
              @generate="generateAnalysis(q, $event)"
              @restore="restoreQuery(q)"
              @correct="correctToTable(q)"
            />
            <label class="ask-field note">
              <span class="ask-field-label">口径说明<span class="ask-optional">选填</span></span>
              <input
                v-model="draftFor(q).note"
                class="ask-input"
                placeholder="例如：含贴现；期末余额口径"
                :maxlength="NOTE_MAX"
                autocomplete="off"
              />
            </label>
          </div>

          <div v-else-if="draftFor(q).action === 'paste'" class="ask-fields sql-block">
            <PastedTableEditor
              :metric="q.metric || q.content"
              :text="draftFor(q).text"
              @update:text="draftFor(q).text = $event"
              @parsed="draftFor(q).parsed = $event"
            />
            <label class="ask-field note">
              <span class="ask-field-label">口径说明<span class="ask-optional">选填</span></span>
              <input
                v-model="draftFor(q).note"
                class="ask-input"
                placeholder="例如：含贴现；期末余额口径"
                :maxlength="NOTE_MAX"
                autocomplete="off"
              />
            </label>
          </div>

          <p v-else-if="draftFor(q).action === 'drop'" class="ask-note drop">
            这个指标会整个移出报告，正文不会提到它，也不会解释它为什么缺失。
          </p>
        </template>

        <div v-else-if="outcome(q)" class="ask-outcome" :class="{ dropped: outcome(q)!.dropped }">
          {{ outcome(q)!.text }}
        </div>
      </div>
    </div>

    <div v-if="isOpen" class="ask-foot">
      <span class="ask-foot-hint">
        {{ remaining > 0 ? `还有 ${remaining} 项没处理` : '都处理好了，可以继续生成' }}
      </span>
      <button
        type="button"
        class="ask-submit"
        :disabled="!canSubmit"
        :title="remaining > 0 ? '请先处理完所有补充项' : ''"
        @click="submit"
      >
        <span v-if="submitting" class="ask-spinner" aria-hidden="true" />
        {{ submitting ? '提交中…' : '提交并继续生成' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.ask {
  border: 1px solid var(--color-primary-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  /* The card fills the assistant column and stays there. `min-width: 0` is
     what lets a wide result table scroll inside the card instead of widening
     it — a flex item's default `min-width: auto` refuses to shrink below its
     content. Repeated on every nested flex box on the way down to the table. */
  min-width: 0;
}

.ask.is-open {
  border-left: 3px solid var(--color-warning);
}

/* ── 抬头 ── */
.ask-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.ask-badge {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.ask-head-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ask-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.ask-sub {
  font-size: 11.5px;
  color: var(--color-text-light);
}

.ask-counter {
  flex-shrink: 0;
  font-size: 11.5px;
  color: var(--color-text-light);
}

.ask-counter strong {
  color: var(--color-primary);
}

/* ── 章节分组 ── */
.ask-chapter {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ask-chapter-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-bottom: 2px;
  border-bottom: 1px solid var(--color-primary-border);
}

.ask-chapter-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text-medium);
}

.ask-chapter-left {
  font-size: 11px;
  color: var(--color-warning);
}

/* ── 单个待补充项 ── */
.ask-item {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fbfaff;
  transition: background 0.15s ease;
}

.ask-item.done {
  background: var(--color-success-bg);
}

.ask-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ask-metric {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.ask-expect {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.ask-tick {
  margin-left: auto;
  color: var(--color-success);
}

.ask-reason {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--color-text-medium);
}

/* ── 二选一 ── */
.ask-choices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.ask-choice {
  padding: 6px 14px;
  border: 1px solid var(--color-primary-border);
  border-radius: 999px;
  background: #fff;
  color: var(--color-text-medium);
  font-family: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.ask-choice:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.ask-choice.active {
  border-color: transparent;
  background: var(--color-primary);
  color: #fff;
  font-weight: 600;
}

.ask-choice.danger:hover {
  border-color: var(--color-error);
  color: var(--color-error);
}

.ask-choice.danger.active {
  background: var(--color-error);
  color: #fff;
}

/* ── 输入 ── */
.ask-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.ask-field {
  flex: 1 1 200px;
  min-width: 160px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ask-field.note {
  flex: 1 1 170px;
}

.ask-field-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-light);
}

.ask-optional {
  font-weight: 500;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--color-bg-gray);
  color: var(--color-text-lighter);
}

.ask-input {
  width: 100%;
  padding: 7px 11px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  background: #fff;
  color: var(--color-text-dark);
  font-family: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.ask-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-light);
}

.ask-input::placeholder {
  color: var(--color-text-lighter);
}

.ask-input.invalid {
  border-color: var(--color-error);
}

.ask-input.invalid:focus {
  box-shadow: 0 0 0 3px var(--color-error-bg);
}

.ask-error,
.ask-note {
  flex-basis: 100%;
  margin: 0;
  font-size: 11.5px;
  line-height: 1.55;
}

.ask-error {
  color: var(--color-error);
}

.ask-note {
  color: var(--color-text-light);
}

.ask-note.drop {
  margin-top: 2px;
}

/* The editors stack rather than sharing a row with the note. */
.ask-fields.sql-block {
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  /* `.ask-fields` wraps, and a wrapping column flex container sizes its line
     to the widest item's max-content — which let a wide result table stretch
     this box to thousands of pixels and push the whole page sideways. There is
     only ever one column here, so wrapping has nothing to do. */
  flex-wrap: nowrap;
}

.ask-outcome {
  align-self: flex-start;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--color-success-bg);
  color: var(--color-success);
  font-size: 12.5px;
}

.ask-outcome.dropped {
  background: var(--color-bg-gray);
  color: var(--color-text-light);
}

/* ── 提交 ── */
.ask-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.ask-foot-hint {
  font-size: 12px;
  color: var(--color-text-light);
}

.ask-submit {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 18px;
  border: 0;
  border-radius: 8px;
  background: var(--gradient-primary);
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: box-shadow 0.15s, opacity 0.15s;
}

.ask-submit:hover:not(:disabled) {
  box-shadow: 0 4px 14px rgba(123, 63, 178, 0.28);
}

.ask-submit:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.ask-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: ask-spin 0.7s linear infinite;
}

@keyframes ask-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 620px) {
  .ask-fields {
    flex-direction: column;
  }

  .ask-foot {
    flex-direction: column-reverse;
    align-items: stretch;
  }

  .ask-submit {
    justify-content: center;
  }
}
</style>
