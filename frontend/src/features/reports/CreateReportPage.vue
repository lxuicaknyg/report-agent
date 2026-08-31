<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useReportStore } from '../../stores/report'
import { useDatasetStore } from '../../stores/dataset'
import type { CreateReportGenerationRequest } from '../../types'

const route = useRoute()
const router = useRouter()
const reportStore = useReportStore()
const datasetStore = useDatasetStore()

const payload = ref<CreateReportGenerationRequest>({
  template_id: String(route.query.template_id || ''),
  dataset_ids: [],
  instruction: '',
  title: '',
  auto_start: true,
})

onMounted(() => {
  void datasetStore.loadDatasets()
})

const canSubmit = computed(() =>
  payload.value.template_id.trim() !== ''
  && payload.value.dataset_ids.length >= 1
  && payload.value.instruction.trim() !== ''
)

function toggleDataset(id: string) {
  const idx = payload.value.dataset_ids.indexOf(id)
  if (idx >= 0) payload.value.dataset_ids.splice(idx, 1)
  else payload.value.dataset_ids.push(id)
}

async function submit() {
  if (!canSubmit.value) return
  const session = await reportStore.createSession(payload.value)
  if (session) {
    router.push({ name: 'report-detail', params: { sessionId: session.session_id } })
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2 class="page-title">创建报告</h2>
        <p class="page-desc">选择模板 + 一个或多个数据源，填写生成指令</p>
      </div>
    </header>

    <section class="card">
      <h3 class="card-title">① 选择模板</h3>
      <div v-if="reportStore.templates.length === 0" class="hint small">
        暂无可用模板，请先<a @click="$router.push({ name: 'report-templates' })" class="link">上传模板</a>。
      </div>
      <div v-else class="tpl-list">
        <label
          v-for="t in reportStore.templates"
          :key="t.template_id"
          class="tpl-row"
          :class="{ active: payload.template_id === t.template_id }"
        >
          <input type="radio" v-model="payload.template_id" :value="t.template_id" class="radio" />
          <div class="tpl-row-body">
            <div class="tpl-row-title">{{ t.title }}</div>
            <div class="tpl-row-meta">{{ t.filename }} · 章节 {{ t.sections?.length ?? 0 }}</div>
          </div>
        </label>
      </div>
    </section>

    <section class="card">
      <h3 class="card-title">② 选择数据源（至少 1 个）</h3>
      <div v-if="datasetStore.datasets.length === 0" class="hint small">
        暂无数据集，请先<a @click="$router.push({ name: 'datasets' })" class="link">注册数据集</a>。
      </div>
      <div v-else class="ds-list">
        <label
          v-for="d in datasetStore.datasets"
          :key="d.dataset_id"
          class="ds-row"
          :class="{ active: payload.dataset_ids.includes(d.dataset_id) }"
        >
          <input type="checkbox" :value="d.dataset_id" :checked="payload.dataset_ids.includes(d.dataset_id)" @change="toggleDataset(d.dataset_id)" class="checkbox" />
          <div class="ds-row-body">
            <div class="ds-row-title">{{ d.name }}</div>
            <div class="ds-row-meta">
              <span class="tag" :class="d.source_type">{{ d.source_type }}</span>
              <span>{{ d.row_count ?? '?' }} 行 · {{ d.columns?.length ?? 0 }} 列</span>
            </div>
          </div>
        </label>
      </div>
    </section>

    <section class="card">
      <h3 class="card-title">③ 生成指令</h3>
      <div class="form-col gap">
        <label class="form-label">报告标题（可选）：</label>
        <input v-model="payload.title" class="text-input" placeholder="例如：2025Q1 资产负债分析报告" />
        <label class="form-label">指令（必填）：</label>
        <textarea v-model="payload.instruction" rows="5" class="text-input" placeholder="例如：请根据模板章节结构，以 2024 年年报口径撰写，附上同比说明" />
        <label class="form-check">
          <input type="checkbox" v-model="payload.auto_start" />
          <span>创建后立即开始（Stub ChapterWriter 占位模式，完成/失败状态会 2s 自动拉取）</span>
        </label>
        <div class="actions">
          <button type="button" class="secondary-btn" @click="$router.back()">返回</button>
          <button type="button" class="primary-btn" :disabled="!canSubmit || reportStore.loadingSession" @click="submit">
            {{ reportStore.loadingSession ? '创建中…' : '创建报告会话' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }

.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }
.page-desc { font-size: 13px; color: var(--color-text-medium); margin: 0; }

.card { background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }
.card-title { font-size: 15px; font-weight: 600; margin: 0 0 14px; color: var(--color-text-dark); }

.hint.small { padding: 16px 12px; font-size: 13px; color: var(--color-text-medium); background: #fbfaff; border-radius: 10px; }
.hint.small .link { color: var(--color-primary); font-weight: 600; cursor: pointer; text-decoration: underline; }

.tpl-list, .ds-list { display: flex; flex-direction: column; gap: 8px; }

.tpl-row, .ds-row {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 12px 14px; border: 1px solid var(--color-primary-border); border-radius: 10px;
  cursor: pointer; transition: border-color .15s, background .15s;
}
.tpl-row:hover, .ds-row:hover { background: #fbfaff; }
.tpl-row.active, .ds-row.active {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}

.radio, .checkbox { margin-top: 4px; }

.tpl-row-body, .ds-row-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }

.tpl-row-title, .ds-row-title { font-size: 14px; font-weight: 600; color: var(--color-text-dark); }

.tpl-row-meta { font-size: 12px; color: var(--color-text-light); }

.ds-row-meta { display: flex; gap: 10px; align-items: center; font-size: 12px; color: var(--color-text-medium); }

.tag { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.tag.excel { background: var(--color-primary-light); color: var(--color-primary); }
.tag.sql { background: #eef5ff; color: #2563eb; }

.form-col { display: flex; flex-direction: column; }
.form-col.gap { gap: 10px; }
.form-label { font-size: 13px; color: var(--color-text-medium); font-weight: 500; }

.text-input {
  padding: 9px 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  font-size: 13.5px;
  font-family: inherit;
  background: #fff;
  width: 100%;
  line-height: 1.55;
}

.form-check {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; color: var(--color-text-dark); cursor: pointer; user-select: none;
}

.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 10px; }

.primary-btn, .secondary-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 10px 18px; border-radius: 10px; font-size: 14px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}
.primary-btn { border: 0; background: var(--gradient-primary); color: #fff; }
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.secondary-btn { border: 1px solid var(--color-primary-border); background: #fff; color: var(--color-primary); }
</style>
