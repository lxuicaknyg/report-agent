<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useConnectionStore } from '../../../stores/connection'
import type {
  AnalysisType,
  ConnectionQueryResult,
  DataConnection,
  SupplementShape,
} from '../../../types'

const props = defineProps<{
  /** What the value will be recorded as, shown so the reading can be checked
   * against the thing that was actually asked for. */
  metric: string
  connectionId: string
  query: string
  /** What this question needs, decided when it was raised. The editor reads
   * the result accordingly and never asks the user to pick it. */
  shape: SupplementShape
  running: boolean
  result: ConnectionQueryResult | null
  /** True while `result` still describes the connection and SQL on screen. */
  fresh: boolean
  /** Which derived analysis is being generated, if any. */
  generating: AnalysisType | null
  /** What the SQL box held before a generated query replaced it. Empty when
   * nothing has been replaced, which is also what hides the undo. */
  replaced: string
  generateError: string
}>()

const emit = defineEmits<{
  (e: 'update:connectionId', value: string): void
  (e: 'update:query', value: string): void
  (e: 'run'): void
  (e: 'generate', value: AnalysisType): void
  (e: 'restore'): void
  /** This question was raised as a single figure and the query answers with a
   * list. Records it as one instead — the correction for a wrong guess, not a
   * mode the user has to choose upfront. */
  (e: 'correct'): void
}>()

const store = useConnectionStore()

onMounted(() => {
  // Cheap and shared: several cards can be open, and the list rarely changes
  // within one conversation.
  if (!store.connections.length) store.load()
})

const usable = computed<DataConnection[]>(() => store.connections)

const extraction = computed(() => props.result?.extraction ?? null)

/** The reading the supplement would be stored with, once one is available. */
const reading = computed(() => {
  const found = extraction.value
  if (!props.fresh || !found?.value) return null
  const dimensions = Object.entries(found.dimensions ?? {})
  return { value: found.value, dimensions }
})

/** The detail table that would be stored, for `shape: 'table'`. */
const table = computed(() => {
  const found = extraction.value
  if (!props.fresh || found?.shape !== 'table' || !found.rows.length) return null
  return { columns: found.columns, count: found.rows.length, truncated: found.truncated }
})

/** Why the current result cannot be used, if it cannot. */
const failure = computed(() => {
  if (!props.fresh || !props.result) return ''
  if (!props.result.success) return props.result.message
  return extraction.value?.error ?? ''
})

/**
 * True when the only thing wrong is that we asked the wrong question.
 *
 * A single-figure question whose query returns rows is usually not a mistake
 * in the SQL — it is a metric that was always a list. Offering the correction
 * right here is what lets the question be raised with a kind at all: a wrong
 * guess costs one click instead of making everyone choose a mode upfront.
 */
const correctable = computed(
  () => props.shape === 'value' && failure.value.includes('按明细清单补充'),
)

const canRun = computed(
  () => !props.running && !!props.connectionId && props.query.trim().length > 0,
)

/**
 * ...and only once the query has run successfully.
 *
 * Rewriting a statement that does not work yet produces a rewrite of a
 * mistake: the generator copies the original's tables and filters, so a wrong
 * query becomes a wrong year-on-year query, and the user is then debugging
 * generated SQL instead of their own.
 *
 * The buttons stay on screen while locked rather than appearing out of
 * nowhere — a feature nobody can see is a feature nobody uses, and the
 * disabled state is what teaches the order of the two steps.
 */
const ranSuccessfully = computed(
  () => props.fresh && !!props.result?.success && !extraction.value?.error,
)

/**
 * Year-on-year applies to a detail query too.
 *
 * The generator keeps the original's grouping, so a breakdown by branch
 * becomes the same breakdown with this period against last beside it. Locking
 * these to a single figure meant anyone whose metric was a table had to write
 * the comparison by hand.
 */
const canGenerate = computed(() => ranSuccessfully.value && !props.generating)

/** Why the generate buttons are locked, if they are. */
const generateHint = computed(() => {
  if (props.generating) return '正在生成…'
  if (!props.connectionId) return '请先选择数据源'
  if (!props.query.trim()) return '请先写好取数 SQL'
  if (!ranSuccessfully.value) return '请先试跑成功，再基于这条 SQL 生成'
  return ''
})

const ANALYSES: { type: AnalysisType; label: string }[] = [
  { type: 'yoy', label: '计算同比' },
  { type: 'mom', label: '计算环比' },
]

const VALUE_PLACEHOLDER = `SELECT Statistics_Dt AS 统计日期, SUM(Deposit_Bal) AS 存款余额
FROM RTL_CUST_AST_MGT_BAL
WHERE Statistics_Dt = '2024-04-15'
GROUP BY Statistics_Dt`

const TABLE_PLACEHOLDER = `SELECT Branch_Name AS 分行, Product_Type AS 产品类型,
       SUM(Loan_Bal) AS 贷款余额
FROM CORP_LOAN_QUALITY_SUMMARY
WHERE Statistics_Dt = '2026-06-30'
GROUP BY Branch_Name, Product_Type`

/** A scalar is checked at a glance; a detail table needs enough rows to see
 * whether the grouping is right. */
const previewRows = computed(() => (props.shape === 'table' ? 10 : 5))

const placeholder = computed(() =>
  props.shape === 'table' ? TABLE_PLACEHOLDER : VALUE_PLACEHOLDER,
)

/** Only a single-value query has a column that is "the value"; in a detail
 * table every column is content, so nothing is highlighted. */
function isValueColumn(index: number, total: number): boolean {
  return props.shape === 'value' && index === total - 1
}

function cell(row: Record<string, unknown>, column: string): string {
  const value = row[column]
  return value === null || value === undefined ? 'NULL' : String(value)
}

/** Ctrl/Cmd+Enter runs, so a query can be tried without leaving the keyboard. */
function onKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && canRun.value) {
    event.preventDefault()
    emit('run')
  }
}
</script>

<template>
  <div class="sql">
    <p v-if="!usable.length" class="sql-empty">
      还没有配置数据源。请先到「数据源」页面新建一个连接，再回来取数。
    </p>

    <template v-else>
      <label class="sql-field">
        <span class="sql-label">数据源</span>
        <select
          class="sql-select"
          :value="connectionId"
          @change="emit('update:connectionId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>请选择一个数据源</option>
          <option v-for="item in usable" :key="item.connection_id" :value="item.connection_id">
            {{ item.name }}（{{ item.database || item.host }}）{{
              item.status === 'failed' ? ' · 上次连接失败' : ''
            }}
          </option>
        </select>
      </label>

      <label class="sql-field">
        <span class="sql-label">
          SQL
          <span v-if="shape === 'value'" class="sql-hint">最后一列是取值，前面的列作为维度记录</span>
          <span v-else class="sql-hint">所有列都会原样写进报告表格，最多 100 行</span>
        </span>
        <textarea
          class="sql-input"
          :value="query"
          rows="4"
          spellcheck="false"
          :placeholder="placeholder"
          @input="emit('update:query', ($event.target as HTMLTextAreaElement).value)"
          @keydown="onKeydown"
        />
      </label>

      <div class="sql-actions">
        <button type="button" class="sql-run" :disabled="!canRun" @click="emit('run')">
          <span v-if="running" class="sql-spinner" aria-hidden="true" />
          {{ running ? '取数中…' : '试跑' }}
        </button>

        <button
          v-for="item in ANALYSES"
          :key="item.type"
          type="button"
          class="sql-derive"
          :disabled="!canGenerate"
          :title="generateHint || `基于上面这条已跑通的 SQL 生成${item.label.slice(2)}查询`"
          @click="emit('generate', item.type)"
        >
          <span v-if="generating === item.type" class="sql-spinner" aria-hidden="true" />
          {{ generating === item.type ? '生成中…' : item.label }}
        </button>

        <button v-if="replaced" type="button" class="sql-undo" @click="emit('restore')">
          还原原始 SQL
        </button>

        <span class="sql-actions-hint">
          {{ generateHint || `只允许 SELECT / WITH 查询${shape === 'value' ? '，需要收敛到一行' : ''}` }}
        </span>
      </div>

      <p v-if="generateError" class="sql-failure">{{ generateError }}</p>

      <p v-else-if="replaced && !fresh" class="sql-note">
        已生成新的 SQL，请先试跑确认结果再提交。
      </p>

      <template v-if="failure">
        <p class="sql-failure">{{ failure }}</p>
        <button v-if="correctable" type="button" class="sql-correct" @click="emit('correct')">
          按明细清单补充
        </button>
      </template>

      <div v-if="fresh && result?.success && result.rows.length" class="sql-preview">
        <div class="sql-table-wrap">
          <table class="sql-table">
            <thead>
              <tr>
                <th
                  v-for="(column, index) in result.columns"
                  :key="column"
                  :class="{ 'is-value': isValueColumn(index, result.columns.length) }"
                >
                  {{ column }}
                  <span
                    v-if="isValueColumn(index, result.columns.length)"
                    class="sql-th-tag"
                  >取值</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in result.rows.slice(0, previewRows)" :key="index">
                <td
                  v-for="(column, col) in result.columns"
                  :key="column"
                  :class="{ 'is-value': isValueColumn(col, result.columns.length) }"
                >{{ cell(row, column) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="result.rows.length > previewRows" class="sql-more">
          共 {{ result.truncated ? `${result.row_count}+` : result.row_count }} 行，仅显示前
          {{ previewRows }} 行
        </p>
      </div>

      <div v-if="reading" class="sql-reading">
        <span class="sql-reading-label">将记录为</span>
        <span class="sql-reading-body">
          <strong>{{ metric }}</strong> = {{ reading.value }}
          <template v-if="reading.dimensions.length">
            <span
              v-for="[name, value] in reading.dimensions"
              :key="name"
              class="sql-dim"
            >{{ name }}={{ value }}</span>
          </template>
        </span>
      </div>

      <div v-if="table" class="sql-reading">
        <span class="sql-reading-label">将记录为</span>
        <span class="sql-reading-body">
          <strong>{{ metric }}</strong> 明细表 · {{ table.count }} 行 × {{ table.columns.length }} 列
          <span class="sql-dim">{{ table.columns.join('、') }}</span>
        </span>
      </div>

      <p v-if="table?.truncated" class="sql-warn">
        结果超过 100 行，只会取前 100 行写进报告，并在表下注明已截断。需要完整明细请先收窄取数范围。
      </p>

      <p v-if="reading && !reading.dimensions.length" class="sql-warn">
        这次取数没有带维度列，该数值只会按指标名「{{ metric }}」使用。把过滤或分组的字段
        一并 SELECT 出来（如统计日期、机构），报告里才能说清它是哪个口径的数。
      </p>
    </template>
  </div>
</template>

<style scoped>
.sql {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 2px;
  /* See the note on `.ask`: the preview table scrolls inside this box rather
     than stretching the card it sits in. */
  min-width: 0;
}

.sql-empty {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--color-text-light);
}

.sql-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sql-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-light);
}

.sql-hint {
  font-weight: 500;
  color: var(--color-text-lighter);
}

.sql-select,
.sql-input {
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

.sql-input {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  resize: vertical;
  min-height: 76px;
  white-space: pre;
  overflow-wrap: normal;
  overflow-x: auto;
}

.sql-select:focus,
.sql-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-light);
}

.sql-input::placeholder {
  color: var(--color-text-lighter);
}

.sql-correct {
  align-self: flex-start;
  padding: 5px 13px;
  border: 1px solid var(--color-primary);
  border-radius: 999px;
  background: #fff;
  color: var(--color-primary);
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.sql-correct:hover {
  background: var(--color-primary);
  color: #fff;
}

.sql-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sql-run {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid var(--color-primary);
  border-radius: 999px;
  background: #fff;
  color: var(--color-primary);
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, opacity 0.15s;
}

.sql-run:hover:not(:disabled) {
  background: var(--color-primary);
  color: #fff;
}

.sql-run:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Secondary to 试跑: generating is a convenience, running is the commitment. */
.sql-derive,
.sql-undo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 13px;
  border: 1px solid var(--color-primary-border);
  border-radius: 999px;
  background: #fff;
  color: var(--color-text-medium);
  font-family: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, opacity 0.15s;
}

.sql-derive:hover:not(:disabled),
.sql-undo:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.sql-derive:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sql-undo {
  color: var(--color-text-light);
}

.sql-note {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--color-text-light);
}

/* Scoped styles do not cross components, so this cannot be inherited from the
   question card — the running indicator was rendering with no size at all. */
.sql-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-primary-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: sql-spin 0.7s linear infinite;
}

@keyframes sql-spin {
  to { transform: rotate(360deg); }
}

.sql-actions-hint {
  font-size: 11px;
  color: var(--color-text-lighter);
}

.sql-failure {
  margin: 0;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 11.5px;
  line-height: 1.55;
}

/* ── 结果预览 ── */
.sql-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sql-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
}

.sql-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.sql-table th,
.sql-table td {
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--color-primary-border);
}

.sql-table tbody tr:last-child td {
  border-bottom: 0;
}

.sql-table th {
  background: var(--color-bg-gray);
  font-weight: 600;
  color: var(--color-text-medium);
}

.sql-table th.is-value,
.sql-table td.is-value {
  color: var(--color-primary);
  font-weight: 600;
}

.sql-th-tag {
  margin-left: 5px;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 10px;
  font-weight: 600;
}

.sql-more {
  margin: 0;
  font-size: 11px;
  color: var(--color-text-lighter);
}

/* ── 读数与提醒 ── */
.sql-reading {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--color-success-bg);
  font-size: 12.5px;
  color: var(--color-success);
}

.sql-reading-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
}

.sql-reading-body {
  min-width: 0;
  word-break: break-word;
}

.sql-dim {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.65);
  font-size: 11.5px;
}

.sql-warn {
  margin: 0;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: 11.5px;
  line-height: 1.6;
}

@media (max-width: 620px) {
  .sql-table th,
  .sql-table td {
    padding: 5px 8px;
  }
}
</style>
