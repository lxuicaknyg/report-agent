<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Message, ProgressChapter, ProgressMessagePayload } from '../../../types'
import { renderMarkdown } from '../../../utils/markdown'

const props = defineProps<{
  message: Message
  /** While the run is in flight the stored payload is a snapshot; prefer live state. */
  live?: ProgressChapter[] | null
  /** Session status, so the flow can close itself off once the report is done. */
  sessionStatus?: string | null
}>()

const payload = computed(() => props.message.payload as unknown as ProgressMessagePayload)
const chapters = computed(() => props.live ?? payload.value.chapters ?? [])

const STATE_TEXT: Record<string, string> = {
  completed: '已完成',
  running: '正在生成中',
  waiting_user: '等待补充数据',
  pending: '等待生成',
}

function stateOf(chapter: ProgressChapter): string {
  return chapter.status ?? (chapter.completed ? 'completed' : 'pending')
}

const doneCount = computed(
  () => chapters.value.filter((item) => stateOf(item) === 'completed').length,
)

const isFinished = computed(
  () => props.sessionStatus === 'completed' && chapters.value.length > 0,
)

/**
 * Chapters the reader folded away. Written chapters stay open by default: the
 * point of the flow is to show each result the moment it lands.
 */
const collapsed = ref<Set<string>>(new Set())

function toggle(chapter: ProgressChapter) {
  if (!chapter.content) return
  const next = new Set(collapsed.value)
  if (next.has(chapter.section_id)) next.delete(chapter.section_id)
  else next.add(chapter.section_id)
  collapsed.value = next
}

function isOpen(chapter: ProgressChapter): boolean {
  return Boolean(chapter.content) && !collapsed.value.has(chapter.section_id)
}
</script>

<template>
  <div class="flow">
    <div v-if="chapters.length" class="flow-meter">
      <span class="flow-meter-label">章节进度</span>
      <span class="flow-meter-count">{{ doneCount }}/{{ chapters.length }}</span>
      <span class="flow-meter-track">
        <span
          class="flow-meter-fill"
          :style="{ width: `${(doneCount / chapters.length) * 100}%` }"
        />
      </span>
    </div>

    <div v-else class="flow-preparing">
      <span class="flow-dots"><span /><span /><span /></span>
      <span>正在准备章节…</span>
    </div>

    <div
      v-for="chapter in chapters"
      :key="chapter.section_id"
      class="flow-step"
      :class="stateOf(chapter)"
    >
      <span class="flow-mark" :class="stateOf(chapter)" aria-hidden="true">
        <svg
          v-if="stateOf(chapter) === 'completed'"
          viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor"
          stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"
        ><polyline points="20 6 9 17 4 12" /></svg>
        <span v-else-if="stateOf(chapter) === 'waiting_user'" class="flow-mark-glyph">!</span>
        <span v-else-if="stateOf(chapter) === 'running'" class="flow-mark-pulse" />
      </span>

      <div class="flow-body">
        <component
          :is="chapter.content ? 'button' : 'div'"
          class="flow-head"
          :class="{ clickable: !!chapter.content }"
          :type="chapter.content ? 'button' : undefined"
          :aria-expanded="chapter.content ? isOpen(chapter) : undefined"
          @click="toggle(chapter)"
        >
          <span class="flow-title">{{ chapter.title }}</span>
          <span class="flow-state" :class="stateOf(chapter)">
            {{ STATE_TEXT[stateOf(chapter)] }}
            <span v-if="stateOf(chapter) === 'running'" class="flow-dots">
              <span /><span /><span />
            </span>
          </span>
          <svg
            v-if="chapter.content"
            class="flow-chevron"
            :class="{ open: isOpen(chapter) }"
            viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor"
            stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
          ><polyline points="6 9 12 15 18 9" /></svg>
        </component>

        <div
          v-if="isOpen(chapter)"
          class="flow-content md-content"
          v-html="renderMarkdown(chapter.content)"
        />
      </div>
    </div>

    <div v-if="isFinished" class="flow-step completed is-final">
      <span class="flow-mark completed" aria-hidden="true">
        <svg
          viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor"
          stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"
        ><polyline points="20 6 9 17 4 12" /></svg>
      </span>
      <div class="flow-body">
        <div class="flow-head">
          <span class="flow-title">全部章节已生成，报告已成文</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.flow {
  display: flex;
  flex-direction: column;
}

.flow-meter {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 12px 2px;
  font-size: 12px;
  color: var(--color-text-light);
}

.flow-meter-count {
  color: var(--color-primary);
  font-weight: 600;
}

.flow-meter-track {
  flex: 1;
  max-width: 160px;
  height: 3px;
  border-radius: 999px;
  background: var(--color-primary-light);
  overflow: hidden;
}

.flow-meter-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--color-primary);
  transition: width 0.35s ease;
}

.flow-preparing {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-medium);
}

/* ── 时间轴：每一章是流程里的一步，靠竖线串成一个整体 ── */
.flow-step {
  position: relative;
  display: flex;
  gap: 10px;
  padding-bottom: 16px;
}

.flow-step::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 19px;
  bottom: 0;
  width: 2px;
  background: var(--color-primary-border);
}

.flow-step:last-child {
  padding-bottom: 0;
}

.flow-step:last-child::before {
  display: none;
}

.flow-mark {
  position: relative;
  z-index: 1;
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-app, #f7f5fb);
  border: 2px solid var(--color-primary-border);
  color: var(--color-text-light);
}

.flow-mark.completed {
  background: var(--color-success-bg);
  border-color: transparent;
  color: var(--color-success);
}

.flow-mark.running {
  background: var(--color-primary-light);
  border-color: var(--color-primary);
}

.flow-mark.waiting_user {
  background: var(--color-warning-bg);
  border-color: transparent;
  color: var(--color-warning);
}

.flow-mark-glyph {
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
}

.flow-mark-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: flow-pulse 1.4s ease-in-out infinite;
}

@keyframes flow-pulse {
  0%, 100% { transform: scale(0.7); opacity: 0.5; }
  50% { transform: scale(1); opacity: 1; }
}

.flow-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.flow-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  font-family: inherit;
  font-size: 13.5px;
  text-align: left;
  color: inherit;
}

.flow-head.clickable {
  cursor: pointer;
}

.flow-head.clickable:hover .flow-title {
  color: var(--color-primary);
}

.flow-title {
  font-weight: 600;
  color: var(--color-text-dark);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.flow-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  font-size: 11.5px;
  color: var(--color-text-light);
}

.flow-state.completed { color: var(--color-success); }
.flow-state.running { color: var(--color-primary); }
.flow-state.waiting_user { color: var(--color-warning); }

.flow-chevron {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--color-text-lighter);
  transition: transform 0.15s ease;
}

.flow-chevron.open {
  transform: rotate(180deg);
}

/* 正文直接落在对话流里，不再套一层卡片背景 */
.flow-content {
  margin-top: 6px;
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--color-text-body);
}

.flow-step.is-final .flow-title {
  color: var(--color-success);
}

.flow-dots {
  display: inline-flex;
  gap: 3px;
  line-height: 1;
}

.flow-dots span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.3;
  animation: flow-dots-bounce 1.2s infinite ease-in-out both;
}

.flow-dots span:nth-child(1) { animation-delay: -0.32s; }
.flow-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes flow-dots-bounce {
  0%, 80%, 100% { opacity: 0.25; transform: scale(0.9); }
  40% { opacity: 1; transform: scale(1.15); }
}
</style>
