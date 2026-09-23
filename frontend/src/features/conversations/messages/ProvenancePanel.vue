<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ChapterDraft, MetricFinding } from '../../../types'
import SourceDetail from './SourceDetail.vue'

const props = defineProps<{ chapters: ChapterDraft[] }>()

const open = ref(false)
/** Which metric rows are expanded, keyed by `${sectionId}::${metric}`. */
const expanded = ref(new Set<string>())

/** Only chapters that actually settled something are worth listing. */
const traceable = computed(() =>
  props.chapters.filter((chapter) => (chapter.findings ?? []).length > 0),
)

const metricCount = computed(() =>
  traceable.value.reduce((total, chapter) => total + (chapter.findings ?? []).length, 0),
)

/**
 * How a metric got its value, for the row's tag.
 *
 * A value fetched by SQL is neither researched nor typed in: it has no
 * evidence row, but it is not hearsay either — the statement that produced it
 * is on file, which is what the tag has to distinguish.
 */
function origin(finding: MetricFinding): { label: string; kind: string } | null {
  if ((finding.evidence_ids ?? []).length) return null
  if ((finding.reads ?? []).some((read) => read.kind === 'sql')) {
    return { label: 'SQL 取数', kind: 'sql' }
  }
  return { label: '用户补充', kind: 'supplied' }
}

function rowKey(sectionId: string, metric: string): string {
  return `${sectionId}::${metric}`
}

function toggleRow(sectionId: string, metric: string) {
  const key = rowKey(sectionId, metric)
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}
</script>

<template>
  <div v-if="traceable.length" class="prov">
    <button type="button" class="prov-toggle" @click="open = !open">
      <span class="prov-caret" :class="{ open }" aria-hidden="true">▸</span>
      数据来源
      <span class="prov-count">{{ metricCount }} 项指标</span>
    </button>

    <div v-if="open" class="prov-body">
      <p class="prov-hint">点开任一指标可查看它的取数条件和返回结果，用于核对报告中的数字。</p>

      <div v-for="chapter in traceable" :key="chapter.section_id" class="prov-chapter">
        <div v-if="traceable.length > 1" class="prov-chapter-title">{{ chapter.title }}</div>

        <div
          v-for="finding in chapter.findings"
          :key="rowKey(chapter.section_id, finding.metric)"
          class="prov-metric"
        >
          <button
            type="button"
            class="prov-metric-head"
            @click="toggleRow(chapter.section_id, finding.metric)"
          >
            <span
              class="prov-caret small"
              :class="{ open: expanded.has(rowKey(chapter.section_id, finding.metric)) }"
              aria-hidden="true"
            >▸</span>
            <span class="prov-metric-name">{{ finding.metric }}</span>
            <span class="prov-metric-value">{{ finding.value }}</span>
            <span
              v-if="origin(finding)"
              class="prov-tag"
              :class="origin(finding)!.kind"
            >{{ origin(finding)!.label }}</span>
          </button>

          <div v-if="expanded.has(rowKey(chapter.section_id, finding.metric))" class="prov-detail">
            <SourceDetail :finding="finding" :chapter="chapter" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prov { margin-top: 10px; }

.prov-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-pill);
  background: #fff; color: var(--color-text-medium);
  font-size: 12.5px; font-family: inherit; cursor: pointer;
}
.prov-toggle:hover { border-color: var(--color-primary-border-strong); color: var(--color-primary); }
.prov-count { color: var(--color-text-lighter); font-size: 11.5px; }

.prov-caret { display: inline-block; transition: transform 0.15s ease; font-size: 10px; }
.prov-caret.open { transform: rotate(90deg); }
.prov-caret.small { color: var(--color-text-lighter); }

.prov-body {
  margin-top: 10px; padding: 14px 16px;
  border: 1px solid var(--color-border); border-radius: var(--radius-lg);
  background: var(--color-bg-sidebar);
}
.prov-hint { margin: 0 0 12px; font-size: 11.5px; color: var(--color-text-light); }

.prov-chapter + .prov-chapter { margin-top: 14px; }
.prov-chapter-title {
  font-size: 12px; font-weight: 700; color: var(--color-text-medium);
  padding-bottom: 6px; border-bottom: 1px solid var(--color-border); margin-bottom: 4px;
}

.prov-metric { border-bottom: 1px solid rgba(217, 226, 236, 0.55); }
.prov-metric:last-child { border-bottom: 0; }

.prov-metric-head {
  display: flex; align-items: baseline; gap: 8px; width: 100%;
  padding: 8px 2px; border: 0; background: transparent;
  font-family: inherit; font-size: 12.5px; text-align: left; cursor: pointer;
}
.prov-metric-head:hover { color: var(--color-primary); }
.prov-metric-name { color: var(--color-text-body); flex-shrink: 0; }
.prov-metric-value {
  color: var(--color-text-dark); font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.prov-tag {
  flex-shrink: 0; padding: 1px 7px; border-radius: var(--radius-pill); font-size: 10.5px;
}
.prov-tag.supplied {
  background: var(--color-warning-bg); color: var(--color-warning);
}
.prov-tag.sql {
  background: var(--color-primary-light); color: var(--color-primary);
}

.prov-detail { padding: 2px 2px 12px 18px; }
.prov-label {
  display: inline-block; margin-right: 6px; font-size: 11px;
  color: var(--color-text-lighter); font-weight: 600;
}
.prov-basis { margin: 0 0 8px; font-size: 12px; color: var(--color-text-medium); }

.prov-evidence + .prov-evidence { margin-top: 10px; }
.prov-evidence-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11.5px; }
.prov-evidence-head code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text-body);
}
.prov-matched { color: var(--color-text-lighter); }

.prov-method {
  margin: 6px 0 8px; padding: 8px 10px; max-height: 220px; overflow: auto;
  background: #fff; border: 1px solid var(--color-border); border-radius: var(--radius-md);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; line-height: 1.5; color: var(--color-text-body); white-space: pre;
}

.prov-table-wrap { overflow-x: auto; }
.prov-table { border-collapse: collapse; font-size: 11.5px; min-width: 100%; }
.prov-table th, .prov-table td {
  padding: 4px 10px; border: 1px solid var(--color-border); text-align: left; white-space: nowrap;
}
.prov-table th { background: var(--color-bg-gray); color: var(--color-text-medium); font-weight: 600; }
.prov-table td { color: var(--color-text-body); background: #fff; }

.prov-empty { margin: 0; font-size: 12px; color: var(--color-text-light); }
</style>
