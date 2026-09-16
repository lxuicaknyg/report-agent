<script setup lang="ts">
import { computed, nextTick, reactive } from 'vue'
import type {
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

const EXPECT_LABEL: Record<string, string> = {
  value: '需要一个数值',
  dataset: '需要另一份数据',
  text: '需要一段说明',
}

const EXPECT_PLACEHOLDER: Record<string, string> = {
  value: '例如：42,060,000 元、12.5%、1.8 亿',
  dataset: '知道结果就直接填数，例如：42,060,000 元',
  text: '例如：本期口径为含贴现的绿色信贷余额',
}

type Draft = { action: 'value' | 'drop' | null; value: string; note: string }
const drafts = reactive<Record<string, Draft>>({})

function draftFor(question: UserQuestion): Draft {
  if (!drafts[question.question_id]) {
    drafts[question.question_id] = { action: null, value: '', note: '' }
  }
  return drafts[question.question_id]
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

function choose(question: UserQuestion, action: 'value' | 'drop') {
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
  const draft = drafts[question.question_id]
  if (draft?.action === 'drop') return { dropped: true, text: '已从报告中删除该指标' }
  if (draft?.action === 'value' && draft.value) {
    return { dropped: false, text: `已补充：${draft.value}` }
  }
  return null
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
              type="button"
              class="ask-choice"
              :class="{ active: draftFor(q).action === 'value' }"
              :aria-pressed="draftFor(q).action === 'value'"
              @click="choose(q, 'value')"
            >我来补充</button>
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
            <p v-else-if="q.expected === 'dataset'" class="ask-note">
              这项本来要另一份数据支撑。上传新数据暂未开放，知道结果可以直接填数，否则建议删除该指标。
            </p>
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
