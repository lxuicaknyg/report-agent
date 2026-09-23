<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import type { ChapterDraft, Evidence, MetricFinding, SqlRead } from '../../../types'

const props = defineProps<{ finding: MetricFinding; chapter: ChapterDraft }>()

/** The reads behind this metric, resolved from the chapter's evidence pool. */
const evidence = computed<Evidence[]>(() => {
  const byId = new Map((props.chapter.evidence ?? []).map((item) => [item.evidence_id, item]))
  return (props.finding.evidence_ids ?? [])
    .map((id) => byId.get(id))
    .filter((item): item is Evidence => Boolean(item))
})

/**
 * Queries the user wrote to settle this metric.
 *
 * These have no evidence row: nothing was read out of a registered dataset,
 * so the statement itself is the record of where the number came from.
 */
const queries = computed<SqlRead[]>(() =>
  (props.finding.reads ?? []).filter((item) => item.kind === 'sql' && item.sql),
)

/** The dimensions a query selected, as `名称=值` pairs. */
function dimensionPairs(read: SqlRead): string[] {
  return Object.entries(read.dimensions ?? {}).map(([name, value]) => `${name}=${value}`)
}

/** The aggregation spec. Stored as a JSON string; shown formatted. */
function readableMethod(method?: string | null): string {
  if (!method) return ''
  try {
    return JSON.stringify(JSON.parse(method), null, 2)
  } catch {
    return method
  }
}

type AggregateValue = {
  rows?: Record<string, unknown>[]
  matched_rows?: number
  sheet_name?: string
  source_rows?: number[][]
  source_rows_truncated?: boolean
  source_columns?: string[]
}

function detail(item: Evidence): AggregateValue {
  return (item.value ?? {}) as AggregateValue
}

function rows(item: Evidence): Record<string, unknown>[] {
  const list = detail(item).rows
  return Array.isArray(list) ? list.slice(0, 20) : []
}

function columns(item: Evidence): string[] {
  const first = rows(item)[0]
  return first ? Object.keys(first) : []
}

/** The worksheet lines behind one result row, as a readable range. */
function lines(item: Evidence, rowIndex: number): string {
  const all = detail(item).source_rows
  const list = Array.isArray(all) ? all[rowIndex] : undefined
  if (!list?.length) return ''
  if (list.length <= 8) return list.join(', ')
  return `${list.slice(0, 6).join(', ')} … ${list[list.length - 1]}（共 ${list.length} 行）`
}

function hasLines(item: Evidence): boolean {
  return Array.isArray(detail(item).source_rows) && detail(item).source_rows!.length > 0
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

/** Which query was just copied, so only that button confirms. */
const copied = ref<number | null>(null)
let clearCopied: ReturnType<typeof setTimeout> | undefined

async function copy(sql: string, index: number) {
  try {
    await navigator.clipboard.writeText(sql)
  } catch {
    // A denied or unavailable clipboard is not worth an error state here; the
    // statement is on screen and selectable either way.
    return
  }
  copied.value = index
  clearTimeout(clearCopied)
  clearCopied = setTimeout(() => (copied.value = null), 1600)
}

onUnmounted(() => clearTimeout(clearCopied))
</script>

<template>
  <div class="sd">
    <p v-if="finding.basis" class="sd-basis">
      <span class="sd-label">依据</span>{{ finding.basis }}
    </p>

    <div v-for="item in evidence" :key="item.evidence_id" class="sd-evidence">
      <div class="sd-head">
        <span class="sd-label">数据源</span>
        <code>{{ detail(item).sheet_name || item.source }}</code>
        <span v-if="detail(item).matched_rows !== undefined" class="sd-dim">
          命中 {{ detail(item).matched_rows }} 行
        </span>
        <span v-if="detail(item).source_columns?.length" class="sd-dim">
          · 列 {{ detail(item).source_columns!.join('、') }}
        </span>
      </div>

      <div v-if="rows(item).length" class="sd-table-wrap">
        <table class="sd-table">
          <thead>
            <tr>
              <th v-for="col in columns(item)" :key="col">{{ col }}</th>
              <th v-if="hasLines(item)" class="sd-lines-col">来源行</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in rows(item)" :key="index">
              <td v-for="col in columns(item)" :key="col">{{ cell(row[col]) }}</td>
              <td v-if="hasLines(item)" class="sd-lines">{{ lines(item, index) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="detail(item).source_rows_truncated" class="sd-note">
        来源行较多，仅列出前若干行。
      </p>

      <details class="sd-spec">
        <summary>取数条件</summary>
        <pre>{{ readableMethod(item.method) }}</pre>
      </details>
    </div>

    <div v-for="(read, index) in queries" :key="index" class="sd-evidence">
      <div class="sd-head">
        <span class="sd-label">数据源</span>
        <code>{{ read.connection_name || read.connection_id || '已配置的数据源' }}</code>
        <span v-if="dimensionPairs(read).length" class="sd-dim">
          · {{ dimensionPairs(read).join('、') }}
        </span>
        <span v-else-if="(read.rows ?? []).length" class="sd-dim">
          · 明细 {{ read.rows!.length }} 行 × {{ (read.columns ?? []).length }} 列
        </span>
        <span v-else class="sd-dim">· 未声明维度</span>
      </div>
      <div class="sd-sql-wrap">
        <pre class="sd-sql">{{ read.sql }}</pre>
        <button type="button" class="sd-copy" @click="copy(read.sql ?? '', index)">
          {{ copied === index ? '已复制' : '复制' }}
        </button>
      </div>

      <div v-if="(read.rows ?? []).length" class="sd-table-wrap">
        <table class="sd-table">
          <thead>
            <tr><th v-for="col in read.columns ?? []" :key="col">{{ col }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in (read.rows ?? []).slice(0, 20)" :key="i">
              <td v-for="col in read.columns ?? []" :key="col">{{ row[col] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="(read.rows ?? []).length > 20" class="sd-note">
        共 {{ read.rows!.length }} 行，仅列出前 20 行。
      </p>
      <p v-if="read.rows_truncated" class="sd-note">
        取数结果超出上限，报告中使用的是前 {{ (read.rows ?? []).length }} 行。
      </p>
    </div>

    <p v-if="!evidence.length && !queries.length" class="sd-empty">
      该指标由用户直接提供，没有对应的取数记录。
    </p>
  </div>
</template>

<style scoped>
.sd-label {
  display: inline-block; margin-right: 6px; font-size: 11px;
  color: var(--color-text-lighter); font-weight: 600;
}
.sd-basis { margin: 0 0 8px; font-size: 12px; color: var(--color-text-medium); line-height: 1.6; }

.sd-evidence + .sd-evidence { margin-top: 12px; }
.sd-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 11.5px; margin-bottom: 6px; }
.sd-head code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--color-text-body); }
.sd-dim { color: var(--color-text-lighter); }

.sd-table-wrap { overflow-x: auto; }
.sd-table { border-collapse: collapse; font-size: 11.5px; min-width: 100%; }
.sd-table th, .sd-table td {
  padding: 4px 10px; border: 1px solid var(--color-border); text-align: left; white-space: nowrap;
}
.sd-table th { background: var(--color-bg-gray); color: var(--color-text-medium); font-weight: 600; }
.sd-table td { color: var(--color-text-body); background: #fff; }
.sd-lines-col, .sd-lines {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text-light); font-size: 11px;
}

.sd-note { margin: 6px 0 0; font-size: 11px; color: var(--color-text-lighter); }

.sd-spec { margin-top: 8px; }
.sd-spec summary {
  font-size: 11.5px; color: var(--color-text-light); cursor: pointer; user-select: none;
}
.sd-spec summary:hover { color: var(--color-primary); }
.sd-spec pre {
  margin: 6px 0 0; padding: 8px 10px; max-height: 200px; overflow: auto;
  background: #fff; border: 1px solid var(--color-border); border-radius: var(--radius-md);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; line-height: 1.5; color: var(--color-text-body); white-space: pre;
}

.sd-empty { margin: 0; font-size: 12px; color: var(--color-text-light); }

/* ── 用户写的取数 SQL ── */
.sd-sql-wrap { position: relative; }

.sd-sql {
  margin: 0; padding: 8px 10px; max-height: 220px; overflow: auto;
  background: #fff; border: 1px solid var(--color-border); border-radius: var(--radius-md);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; line-height: 1.6; color: var(--color-text-body);
  white-space: pre-wrap; word-break: break-word;
}

.sd-copy {
  position: absolute; top: 6px; right: 6px;
  padding: 2px 8px; border: 1px solid var(--color-border); border-radius: var(--radius-pill);
  background: #fff; color: var(--color-text-light);
  font-family: inherit; font-size: 10.5px; cursor: pointer;
  opacity: 0; transition: opacity 0.15s, color 0.15s, border-color 0.15s;
}

.sd-sql-wrap:hover .sd-copy,
.sd-copy:focus-visible { opacity: 1; }

.sd-copy:hover { border-color: var(--color-primary); color: var(--color-primary); }
</style>
