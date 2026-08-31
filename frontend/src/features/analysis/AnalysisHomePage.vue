<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAnalysisStore } from '../../stores/analysis'
import { useDatasetStore } from '../../stores/dataset'
import type { AnalysisRequest } from '../../types'

const store = useAnalysisStore()
const datasetStore = useDatasetStore()

onMounted(() => {
  void datasetStore.loadDatasets()
})

const profileDatasetId = ref('')
const queryPayload = ref<AnalysisRequest>({
  question: '',
  dataset_id: '',
  sql: '',
  limit: 500,
})

const nlQuestion = ref('')
const nlSubmitting = ref(false)
const nlResult = ref<string>('')

const profileMissingEntries = computed(() => {
  const m = store.currentProfile?.missing_values
  if (!m) return [] as Array<{ key: string; value: number }>
  return Object.entries(m)
    .map(([k, v]) => ({ key: k, value: Number(v) || 0 }))
    .filter((e) => e.value > 0)
    .sort((a, b) => b.value - a.value)
})

const profileDistinctTop = computed(() => {
  const d = store.currentProfile?.distinct_values
  if (!d) return [] as Array<{ key: string; value: number }>
  return Object.entries(d)
    .map(([k, v]) => ({ key: k, value: Number(v) || 0 }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
})

const answerMarkdown = computed(() => store.currentResult?.answer ?? '')

function onProfile() {
  const id = profileDatasetId.value.trim()
  if (!id) return
  void store.runProfile(id)
}

function onQuery() {
  if (!queryPayload.value.sql && !queryPayload.value.question) return
  void store.runQuery({ ...queryPayload.value })
}

async function onNlQuery() {
  const q = nlQuestion.value.trim()
  if (!q || !queryPayload.value.dataset_id) return
  nlSubmitting.value = true
  nlResult.value = ''
  try {
    nlResult.value = 'NL→SQL 功能待后端接口就绪后启用，当前可在「执行 SQL 查询」Tab 中手动输入 SQL。'
  } finally {
    nlSubmitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2 class="page-title">数据分析</h2>
        <p class="page-desc">对已注册的数据集执行 Profile、自然语言查询或只读 SQL</p>
      </div>
    </header>

    <section class="card">
      <h3 class="card-title">① 数据集 Profile</h3>
      <div class="form-row">
        <label class="form-label">选择数据集：</label>
        <select v-model="profileDatasetId" class="text-input select-w" :disabled="datasetStore.loading">
          <option value="">— 请选择 —</option>
          <option v-for="d in datasetStore.datasets" :key="d.dataset_id" :value="d.dataset_id">
            {{ d.name }}（{{ d.source_type }} · {{ d.row_count ?? '?' }} 行）
          </option>
        </select>
        <button type="button" class="primary-btn" :disabled="store.loadingProfile || !profileDatasetId" @click="onProfile">
          {{ store.loadingProfile ? '分析中…' : '执行 Profile' }}
        </button>
      </div>
      <div v-if="datasetStore.datasets.length === 0 && !datasetStore.loading" class="muted">
        暂无可选数据集，请先到「数据集管理」上传 Excel 或注册 SQL 数据源
      </div>
      <div v-if="store.error" class="error-banner">{{ store.error }}
        <button type="button" class="mini-btn" @click="store.clearError()">关闭</button>
      </div>
      <div v-if="store.currentProfile" class="profile-wrap">
        <div class="profile-head">
          <div class="kv"><span class="k">名称：</span><span class="v">{{ store.currentProfile.dataset.name }}</span></div>
          <div class="kv"><span class="k">来源：</span><span class="v">{{ store.currentProfile.dataset.source_type }} · {{ store.currentProfile.dataset.row_count ?? '—' }} 行</span></div>
          <div class="kv"><span class="k">字段数：</span><span class="v">{{ store.currentProfile.dataset.columns?.length ?? 0 }}</span></div>
        </div>
        <div v-if="store.currentProfile.warnings?.length" class="warnings">
          <div v-for="(w, i) in store.currentProfile.warnings" :key="i" class="warn-item">{{ w }}</div>
        </div>
        <div class="stats-grid">
          <div v-if="profileMissingEntries.length" class="stats-card">
            <h4 class="stats-title">缺失值（Top 字段）</h4>
            <ul class="stats-list">
              <li v-for="(e, i) in profileMissingEntries.slice(0, 8)" :key="i">
                <span class="stats-k">{{ e.key }}</span><span class="stats-v">{{ e.value }}</span>
              </li>
            </ul>
          </div>
          <div v-if="profileDistinctTop.length" class="stats-card">
            <h4 class="stats-title">字段去重数（Top 10）</h4>
            <ul class="stats-list">
              <li v-for="(e, i) in profileDistinctTop" :key="i">
                <span class="stats-k">{{ e.key }}</span><span class="stats-v">{{ e.value }}</span>
              </li>
            </ul>
          </div>
        </div>
        <div v-if="store.currentProfile.sample_rows?.length" class="sample-block">
          <h4 class="stats-title">样例行预览（前 {{ Math.min(5, store.currentProfile.sample_rows.length) }} 条）</h4>
          <div class="table-wrap">
            <table class="data-table small">
              <thead>
                <tr>
                  <th v-for="c in Object.keys(store.currentProfile.sample_rows[0] ?? {})" :key="c">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in store.currentProfile.sample_rows.slice(0, 5)" :key="i">
                  <td v-for="c in Object.keys(store.currentProfile.sample_rows[0] ?? {})" :key="c" class="mono small">
                    {{ String(row[c] ?? '') }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <h3 class="card-title">② 自然语言查询（NL → SQL）</h3>
      <div class="form-col">
        <label class="form-label">选择数据集：</label>
        <select v-model="queryPayload.dataset_id" class="text-input select-w" :disabled="datasetStore.loading">
          <option value="">— 请选择 —</option>
          <option v-for="d in datasetStore.datasets" :key="d.dataset_id" :value="d.dataset_id">
            {{ d.name }}（{{ d.source_type }} · {{ d.row_count ?? '?' }} 行）
          </option>
        </select>
        <label class="form-label">描述你想查询的问题：</label>
        <textarea
          v-model="nlQuestion"
          rows="4"
          class="text-input"
          placeholder="例如：各网点季度销售额 Top 10，含客均单价趋势"
        />
        <div class="form-row">
          <button
            type="button"
            class="primary-btn"
            :disabled="nlSubmitting || !queryPayload.dataset_id || !nlQuestion.trim()"
            @click="onNlQuery"
            title="NL→SQL 功能待后端接口就绪后启用"
          >
            {{ nlSubmitting ? '解析中…' : '转成 SQL 并执行（待接口）' }}
          </button>
        </div>
      </div>
      <div v-if="nlResult" class="notice-box">{{ nlResult }}</div>
    </section>

    <section class="card">
      <h3 class="card-title">③ 直接执行分析查询（自然语言 / SQL）</h3>
      <div class="form-col">
        <label class="form-label">选择数据集：</label>
        <select v-model="queryPayload.dataset_id" class="text-input select-w" :disabled="datasetStore.loading">
          <option value="">— 请选择 —</option>
          <option v-for="d in datasetStore.datasets" :key="d.dataset_id" :value="d.dataset_id">
            {{ d.name }}（{{ d.source_type }} · {{ d.row_count ?? '?' }} 行）
          </option>
        </select>
        <label class="form-label">问题（非必填，模型会结合 SQL 或问题生成解释 + 查询结果）：</label>
        <textarea
          v-model="queryPayload.question"
          rows="2"
          class="text-input"
          placeholder="例如：最近一季度各机构贷款投放额排名，Top 5"
        />
        <label class="form-label">SQL（只读 SELECT / WITH，和问题至少填一个）：</label>
        <textarea v-model="queryPayload.sql" rows="5" class="text-input mono" placeholder="SELECT * FROM Sheet1 LIMIT 200" />
        <div class="form-row">
          <label class="form-label">返回行数 limit：</label>
          <input v-model.number="queryPayload.limit" type="number" min="1" max="10000" class="number-input" />
          <button
            type="button"
            class="primary-btn"
            :disabled="store.loadingQuery || !queryPayload.dataset_id || (!queryPayload.sql?.trim() && !queryPayload.question?.trim())"
            @click="onQuery"
          >
            {{ store.loadingQuery ? '执行中…' : '执行查询' }}
          </button>
        </div>
      </div>
      <div v-if="store.error" class="error-banner">{{ store.error }}
        <button type="button" class="mini-btn" @click="store.clearError()">关闭</button>
      </div>
      <div v-if="store.currentResult?.answer" class="answer-box md-content" v-html="answerMarkdown">
      </div>
      <div v-if="store.currentResult?.query_result" class="table-wrap">
        <div class="meta">
          <template v-if="store.currentResult.query_result.sql">
            执行 SQL：<code class="mono">{{ store.currentResult.query_result.sql }}</code>
            <span class="dot">·</span>
          </template>
          <span>用时 {{ Math.round(store.currentResult.query_result.execution_time_ms ?? 0) }}ms</span>
          <span class="dot">·</span>
          <span>{{ store.currentResult.query_result.row_count }} 行</span>
        </div>
        <table class="data-table small">
          <thead><tr><th v-for="c in store.currentResult.query_result.columns" :key="c">{{ c }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, i) in store.currentResult.query_result.rows.slice(0, 50)" :key="i">
              <td v-for="c in store.currentResult.query_result.columns" :key="c" class="mono small">{{ String(row[c] ?? '') }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="store.currentResult.query_result.row_count > 50" class="hint small">仅展示前 50 行。</div>
        <div v-if="store.currentResult.query_result.row_count === 0" class="muted" style="padding:10px 0 0">
          查询结果为空。
        </div>
      </div>
      <div v-if="store.currentResult?.evidence?.length" class="evidence-block">
        <h4 class="stats-title">引用来源（{{ store.currentResult.evidence.length }}）</h4>
        <ul class="evidence-list">
          <li v-for="e in store.currentResult.evidence" :key="e.evidence_id" class="evidence-item">
            <span class="evidence-kind">{{ e.kind }}</span>
            <span class="evidence-title">{{ e.title }}</span>
            <span class="evidence-source" v-if="e.source">— {{ e.source }}</span>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }

.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }
.page-desc { font-size: 13px; color: var(--color-text-medium); margin: 0; }

.card { background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }
.card-title { font-size: 15px; font-weight: 600; margin: 0 0 12px; color: var(--color-text-dark); }

.form-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.form-col { display: flex; flex-direction: column; gap: 8px; }
.form-label { font-size: 13px; color: var(--color-text-medium); font-weight: 500; }

.text-input, .number-input {
  padding: 8px 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  background: #fff;
  color: var(--color-text-dark);
}
.text-input { width: 100%; box-sizing: border-box; }
.text-input.select-w { max-width: 480px; }

.number-input { max-width: 160px; }

.muted {
  font-size: 12.5px;
  color: var(--color-text-light);
  padding: 8px 2px;
}

.primary-btn {
  display: inline-flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 9px;
  border: 0; background: var(--gradient-primary); color: #fff; font-size: 13px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }

.mini-btn {
  padding: 3px 9px;
  border-radius: 6px;
  border: 1px solid rgba(220, 38, 38, 0.4);
  background: transparent;
  color: #b91c1c;
  font-size: 12px;
  cursor: pointer;
  margin-left: 10px;
}

.error-banner {
  margin-top: 10px;
  padding: 9px 12px;
  background: #fef2f2;
  border: 1px solid rgba(220, 38, 38, 0.25);
  border-radius: 8px;
  color: #b91c1c;
  font-size: 12.5px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.profile-wrap { margin-top: 14px; padding: 14px 16px; background: var(--color-primary-light); border-radius: 12px; display: flex; flex-direction: column; gap: 10px; }
.profile-head { display: flex; gap: 18px; flex-wrap: wrap; }
.kv { font-size: 13px; display: flex; gap: 8px; }
.k { color: var(--color-text-medium); flex-shrink: 0; }
.v { color: var(--color-text-dark); font-weight: 500; }

.warnings { display: flex; flex-direction: column; gap: 4px; }
.warn-item { font-size: 12.5px; color: #b45309; background: #fff7ed; padding: 6px 10px; border-radius: 6px; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.stats-card { background: #fff; border: 1px solid var(--color-primary-border); border-radius: 10px; padding: 10px 12px; }
.stats-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: var(--color-text-dark); }
.stats-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.stats-list li { display: flex; justify-content: space-between; font-size: 12.5px; }
.stats-k { color: var(--color-text-medium); }
.stats-v { color: var(--color-text-dark); font-weight: 500; }

.sample-block { background: #fff; border: 1px solid var(--color-primary-border); border-radius: 10px; padding: 10px 12px; }

.notice-box {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--color-info-bg);
  border: 1px solid rgba(63, 110, 178, 0.25);
  color: var(--color-info);
  border-radius: 8px;
  font-size: 13px;
}

.table-wrap { margin-top: 14px; overflow-x: auto; }
.meta { font-size: 12.5px; color: var(--color-text-medium); padding: 8px 0 10px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.meta code { background: #f5f3fa; padding: 2px 6px; border-radius: 4px; color: #4b3f66; word-break: break-all; }
.dot { color: #c7c2d2; }

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; color: var(--color-text-dark); }
.data-table th { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--color-border); color: var(--color-text-medium); font-weight: 600; font-size: 12px; }
.data-table td { padding: 6px 10px; border-bottom: 1px solid var(--color-border); }
.data-table.small td { padding: 5px 9px; }

.mono { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12.5px; }
.mono.small { font-size: 12px; }

.answer-box { margin-top: 12px; padding: 12px 14px; background: #fdfcff; border: 1px solid var(--color-primary-border); border-radius: 10px; }
.answer-box :deep(.md-h1) { font-size: 18px; margin: 4px 0 10px; }
.answer-box :deep(.md-h2) { font-size: 16px; margin: 10px 0 6px; }
.answer-box :deep(.md-h3) { font-size: 14.5px; margin: 8px 0 6px; }
.answer-box :deep(.md-h4) { font-size: 13.5px; margin: 8px 0 4px; }
.answer-box :deep(.md-p) { margin: 6px 0; line-height: 1.65; color: var(--color-text-dark); }
.answer-box :deep(.md-strong) { font-weight: 600; color: var(--color-text-dark); }
.answer-box :deep(.md-em) { font-style: italic; }
.answer-box :deep(.md-code) { background: #f5f3fa; padding: 1px 5px; border-radius: 4px; color: #4b3f66; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12.5px; }
.answer-box :deep(.md-ul), .answer-box :deep(.md-ol) { padding-left: 22px; margin: 6px 0; }
.answer-box :deep(.md-li) { line-height: 1.7; font-size: 13px; }
.answer-box :deep(.md-link) { color: var(--color-primary); text-decoration: underline; }

.evidence-block { margin-top: 14px; padding: 10px 12px; border: 1px dashed var(--color-primary-border); border-radius: 10px; }
.evidence-list { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.evidence-item { font-size: 12.5px; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.evidence-kind {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--color-primary-light);
  color: var(--color-primary, #5b21b6);
  font-weight: 600;
  font-size: 11.5px;
  text-transform: uppercase;
}
.evidence-title { color: var(--color-text-dark); }
.evidence-source { color: var(--color-text-light); }

.hint.small { padding: 8px 0 0; font-size: 12px; color: var(--color-text-light); }
</style>
