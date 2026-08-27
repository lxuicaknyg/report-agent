<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { DataReadRequest } from '../../types'
import { datasetApi } from '../../services/api/datasets'
import type { SheetInfo, ColumnSchema, DataReadResult } from '../../types'

const route = useRoute()
const datasetId = computed(() => String(route.params.datasetId || ''))

const loadingSheets = ref(false)
const sheets = ref<SheetInfo[]>([])
const selectedSheet = ref<string | null>(null)

const loadingSchema = ref(false)
const schema = ref<ColumnSchema[]>([])

const loadingPreview = ref(false)
const preview = ref<DataReadResult | null>(null)

const offset = ref(0)
const limit = ref(100)
const selectedColumns = ref<string[]>([])

interface FilterRow {
  id: number
  column: string
  operator: string
  value: string
}

const FILTER_OPERATORS = [
  { label: '等于 =', value: 'eq' },
  { label: '不等于 !=', value: 'ne' },
  { label: '大于 >', value: 'gt' },
  { label: '大于等于 >=', value: 'gte' },
  { label: '小于 <', value: 'lt' },
  { label: '小于等于 <=', value: 'lte' },
  { label: '包含（字符串）', value: 'contains' },
  { label: '开头是', value: 'startswith' },
  { label: '结尾是', value: 'endswith' },
  { label: '属于列表（逗号分隔）', value: 'in' },
  { label: '为空 IS NULL', value: 'isnull' },
  { label: '不为空 IS NOT NULL', value: 'notnull' },
]

let _filterIdSeq = 0
const filterRows = ref<FilterRow[]>([])

function addFilterRow() {
  const defaultCol = schema.value[0]?.name ?? ''
  filterRows.value.push({
    id: ++_filterIdSeq,
    column: defaultCol,
    operator: 'eq',
    value: '',
  })
}

function removeFilterRow(id: number) {
  const idx = filterRows.value.findIndex((r) => r.id === id)
  if (idx >= 0) filterRows.value.splice(idx, 1)
}

function toggleColumn(colName: string) {
  const idx = selectedColumns.value.indexOf(colName)
  if (idx >= 0) {
    selectedColumns.value.splice(idx, 1)
  } else {
    selectedColumns.value.push(colName)
  }
}

function selectAllColumns() {
  selectedColumns.value = schema.value.map((c) => c.name)
}

function clearAllColumns() {
  selectedColumns.value = []
}

function buildRequest(): DataReadRequest {
  const filters: Record<string, unknown> = {}
  for (const row of filterRows.value) {
    if (!row.column) continue
    const op = row.operator
    if (op === 'isnull') {
      filters[row.column] = { op: 'isnull' }
    } else if (op === 'notnull') {
      filters[row.column] = { op: 'notnull' }
    } else if (op === 'in') {
      const parts = row.value.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
      filters[row.column] = { op, value: parts }
    } else {
      filters[row.column] = { op, value: row.value }
    }
  }

  return {
    sheet_name: selectedSheet.value,
    offset: offset.value,
    limit: limit.value,
    columns: selectedColumns.value.length > 0 ? selectedColumns.value : null,
    filters: Object.keys(filters).length > 0 ? filters : undefined,
  }
}

async function loadSheets() {
  loadingSheets.value = true
  try {
    const res = await datasetApi.listSheets(datasetId.value)
    if (res.success && res.data) {
      sheets.value = res.data
      selectedSheet.value = res.data[0]?.sheet_name ?? null
    }
  } finally {
    loadingSheets.value = false
  }
}

async function loadSchema() {
  if (!selectedSheet.value) return
  loadingSchema.value = true
  try {
    const res = await datasetApi.getSchema(datasetId.value, selectedSheet.value)
    if (res.success && res.data) {
      schema.value = res.data
      filterRows.value = []
      selectedColumns.value = []
    }
  } finally {
    loadingSchema.value = false
  }
}

async function loadPreview() {
  loadingPreview.value = true
  preview.value = null
  try {
    const req = buildRequest()
    const res = await datasetApi.previewDataset(datasetId.value, req)
    if (res.success && res.data) preview.value = res.data
  } finally {
    loadingPreview.value = false
  }
}

function selectSheet() {
  void loadSchema()
}

onMounted(() => {
  void loadSheets().then(() => {
    if (selectedSheet.value) {
      void loadSchema()
    }
  })
})
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2 class="page-title">数据集详情</h2>
        <p class="page-desc">{{ datasetId }}</p>
      </div>
    </header>

    <section class="card">
      <div class="tabs">
        <div class="tabs-label">Sheet：</div>
        <select v-model="selectedSheet" @change="selectSheet" class="select-input" :disabled="loadingSheets">
          <option v-for="s in sheets" :key="s.sheet_name" :value="s.sheet_name">
            {{ s.sheet_name }}（{{ s.row_count ?? '?' }} 行）
          </option>
        </select>
      </div>
    </section>

    <section class="card">
      <h3 class="card-title">字段 Schema</h3>
      <div v-if="loadingSchema" class="hint">加载中…</div>
      <table v-else class="data-table">
        <thead>
          <tr><th>字段名</th><th>类型</th><th>可空</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in schema" :key="c.name">
            <td class="mono">{{ c.name }}</td>
            <td class="tag type">{{ c.data_type }}</td>
            <td>{{ c.nullable ? '是' : '否' }}</td>
            <td>{{ c.description || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <div class="section-head">
        <h3 class="card-title">分页预览</h3>
      </div>

      <div class="sub-section">
        <div class="sub-section-head">
          <span class="sub-title">返回字段 columns（不选则默认全部）</span>
          <div class="sub-actions">
            <button type="button" class="mini-btn" @click="selectAllColumns" :disabled="schema.length === 0">全选</button>
            <button type="button" class="mini-btn" @click="clearAllColumns" :disabled="selectedColumns.length === 0">清空</button>
          </div>
        </div>
        <div v-if="schema.length === 0" class="muted">请先选择 Sheet 并加载 Schema</div>
        <div v-else class="checkbox-grid">
          <label
            v-for="c in schema"
            :key="c.name"
            class="checkbox-item"
            :class="{ checked: selectedColumns.includes(c.name) }"
          >
            <input
              type="checkbox"
              :value="c.name"
              :checked="selectedColumns.includes(c.name)"
              @change="toggleColumn(c.name)"
            />
            <span class="cb-col-name mono">{{ c.name }}</span>
            <span class="cb-col-type tag type">{{ c.data_type }}</span>
          </label>
        </div>
        <div v-if="selectedColumns.length > 0" class="selection-count">
          已选 {{ selectedColumns.length }} / {{ schema.length }} 个字段
        </div>
      </div>

      <div class="sub-section">
        <div class="sub-section-head">
          <span class="sub-title">筛选条件 filters（AND 关系）</span>
          <div class="sub-actions">
            <button type="button" class="mini-btn primary" @click="addFilterRow" :disabled="schema.length === 0">
              添加条件
            </button>
          </div>
        </div>
        <div v-if="schema.length === 0" class="muted">请先选择 Sheet 并加载 Schema</div>
        <div v-else-if="filterRows.length === 0" class="muted">尚未添加筛选条件，默认返回全部行</div>
        <div v-else class="filter-rows">
          <div v-for="row in filterRows" :key="row.id" class="filter-row">
            <select v-model="row.column" class="select-input filter-field">
              <option v-for="c in schema" :key="c.name" :value="c.name">{{ c.name }}</option>
            </select>
            <select v-model="row.operator" class="select-input filter-op">
              <option v-for="op in FILTER_OPERATORS" :key="op.value" :value="op.value">{{ op.label }}</option>
            </select>
            <input
              v-if="row.operator !== 'isnull' && row.operator !== 'notnull'"
              v-model="row.value"
              type="text"
              class="text-input filter-value"
              :placeholder="row.operator === 'in' ? 'v1, v2, v3' : '输入值'"
            />
            <div v-else class="filter-value-ph"></div>
            <button type="button" class="mini-btn danger" @click="removeFilterRow(row.id)">移除</button>
          </div>
        </div>
      </div>

      <div class="sub-section">
        <div class="sub-section-head">
          <span class="sub-title">分页参数</span>
        </div>
        <div class="form-row">
          <label class="form-label">偏移 offset：</label>
          <input v-model.number="offset" type="number" min="0" class="number-input" />
          <label class="form-label">数量 limit：</label>
          <input v-model.number="limit" type="number" min="1" max="10000" class="number-input" />
          <button type="button" class="primary-btn" @click="loadPreview" :disabled="loadingPreview">
            {{ loadingPreview ? '查询中…' : '执行查询' }}
          </button>
        </div>
      </div>

      <div v-if="loadingPreview" class="hint">加载中…</div>
      <table v-else-if="preview" class="data-table small">
        <thead>
          <tr>
            <th v-for="col in preview.columns" :key="col">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in preview.rows" :key="i">
            <td v-for="col in preview.columns" :key="col" class="mono small">{{ String(row[col] ?? '') }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="!loadingPreview" class="muted">点击上方「执行查询」查看结果</div>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }

.page-head { display: flex; align-items: flex-end; justify-content: space-between; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }
.page-desc { font-size: 13px; color: var(--color-text-medium); margin: 0; }

.card { background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }

.card-title { font-size: 15px; font-weight: 600; margin: 0; color: var(--color-text-dark); }

.section-head {
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
}

.sub-section {
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sub-section:last-child {
  margin-bottom: 0;
}

.sub-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.sub-actions {
  display: flex;
  gap: 8px;
}

.mini-btn {
  padding: 5px 12px;
  border-radius: 7px;
  border: 1px solid var(--color-primary-border);
  background: #fff;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.mini-btn:hover { background: var(--color-primary-light); }
.mini-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.mini-btn.primary {
  background: var(--gradient-primary);
  color: #fff;
  border-color: transparent;
}
.mini-btn.primary:hover { filter: brightness(1.05); }

.mini-btn.danger {
  border-color: rgba(208, 80, 80, 0.3);
  color: var(--color-error);
  background: #fff;
}
.mini-btn.danger:hover { background: var(--color-error-bg); }

.muted {
  font-size: 12.5px;
  color: var(--color-text-light);
  padding: 10px 4px;
}

.checkbox-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  font-size: 12.5px;
}

.checkbox-item:hover {
  border-color: var(--color-primary-border);
  background: var(--color-primary-light);
}

.checkbox-item.checked {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}

.checkbox-item input {
  accent-color: var(--color-primary);
  cursor: pointer;
}

.cb-col-name {
  flex: 1;
  color: var(--color-text-dark);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selection-count {
  font-size: 12px;
  color: var(--color-text-medium);
  padding-top: 4px;
}

.filter-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-field {
  min-width: 150px;
  flex: 1;
  max-width: 240px;
}

.filter-op {
  min-width: 150px;
}

.filter-value {
  flex: 1;
  min-width: 180px;
}

.filter-value-ph {
  flex: 1;
  min-width: 180px;
}

.tabs { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.tabs-label { font-size: 13px; font-weight: 600; color: var(--color-text-medium); }

.select-input, .number-input, .text-input {
  padding: 8px 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  background: #fff;
  color: var(--color-text-dark);
  transition: border-color 0.15s;
}

.select-input:focus, .number-input:focus, .text-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.form-label { font-size: 13px; color: var(--color-text-medium); font-weight: 500; }

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; color: var(--color-text-dark); margin-top: 4px; }
.data-table th { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--color-border); color: var(--color-text-medium); font-weight: 600; font-size: 12px; }
.data-table td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); }
.data-table.small td { padding: 6px 10px; }

.mono { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12.5px; }
.mono.small { font-size: 12px; }

.tag.type { display: inline-block; padding: 2px 9px; border-radius: 999px; background: #f4f2f8; color: #5b4b7b; font-size: 11px; font-weight: 600; }

.hint { padding: 24px; text-align: center; color: var(--color-text-medium); font-size: 13px; }

.primary-btn {
  display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 9px;
  border: 0; background: var(--gradient-primary); color: #fff; font-size: 13px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
