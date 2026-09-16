<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useReportStore } from '../../stores/report'
import type { ReportTemplate, ReportTemplateSection } from '../../types'

const router = useRouter()
const store = useReportStore()

onMounted(() => {
  void store.loadTemplates()
})

onUnmounted(() => {
  store.clearError()
})

async function onUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const tpl = await store.uploadTemplate(file)
  if (tpl) {
    void store.loadTemplates()
  }
  const target = e.target as HTMLInputElement
  target.value = ''
}

function goCreate() {
  router.push({ name: 'conversation-new' })
}

function sortedSections(t: ReportTemplate): ReportTemplateSection[] {
  if (!t.sections?.length) return []
  return [...t.sections].sort((a, b) => {
    if (a.order !== b.order) return a.order - b.order
    return (a.level ?? 1) - (b.level ?? 1)
  })
}

function levelIndent(level: number | undefined): number {
  const lv = level ?? 1
  return Math.max(0, lv - 1) * 16
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2 class="page-title">报告模板</h2>
        <p class="page-desc">上传 DOCX / MD / TXT 模板，解析章节结构后创建报告会话</p>
      </div>
      <div class="page-head-actions">
        <label for="tpl-upload" class="primary-btn upload-label" :class="{ 'is-loading': store.loadingTemplate || store.loadingTemplates }">
          {{ store.loadingTemplate ? '上传中…' : '上传模板' }}
        </label>
        <input
          id="tpl-upload"
          type="file"
          accept=".docx,.md,.markdown,.txt"
          style="display:none"
          :disabled="store.loadingTemplate"
          @change="onUpload"
        />
        <button type="button" class="secondary-btn" @click="goCreate">去对话创建报告</button>
      </div>
    </header>

    <section class="card">
      <div v-if="store.error" class="error-banner">
        {{ store.error }}
        <button type="button" class="mini-btn" @click="store.clearError()">关闭</button>
      </div>
      <div v-if="store.loadingTemplates && store.templates.length === 0" class="hint">加载模板列表中…</div>
      <div v-else-if="store.templates.length === 0" class="hint empty">
        暂无模板。点击右上角上传 <code>.docx</code> / <code>.md</code> / <code>.txt</code> 文件。
      </div>
      <div v-else class="grid">
        <div v-for="t in store.templates" :key="t.template_id" class="tpl-card">
          <div class="tpl-head">
            <div class="tpl-title" :title="t.title">{{ t.title }}</div>
            <div class="tpl-file">{{ t.filename }}</div>
          </div>
          <div class="tpl-meta">
            <span>章节 {{ t.sections?.length ?? 0 }} 个</span>
            <span>上传 {{ new Date(t.created_at).toLocaleString() }}</span>
            <span v-if="store.totalTemplates > store.templates.length" class="meta-extra">共 {{ store.totalTemplates }} 个</span>
          </div>

          <div class="tpl-outline">
            <div class="outline-title">章节结构预览</div>
            <div v-if="!t.sections?.length" class="outline-empty muted">
              章节 Heading 层级解析待后端 P2 第⑧条接口抵达，当前仅展示总数
            </div>
            <ul v-else class="outline-tree">
              <li
                v-for="s in sortedSections(t)"
                :key="s.section_id"
                class="outline-item"
                :style="{ paddingLeft: levelIndent(s.level) + 'px' }"
              >
                <span class="outline-level" v-if="s.level">H{{ s.level }}</span>
                <span class="outline-order">{{ s.order + 1 }}.</span>
                <span class="outline-name">{{ s.title }}</span>
              </li>
            </ul>
          </div>

          <div class="tpl-actions">
            <button type="button" class="primary-btn block" @click="goCreate">
              在对话中创建报告
            </button>
            <button
              type="button"
              class="secondary-btn block"
              disabled
              title="删除模板接口待后端 P1 第④条抵达"
            >
              删除模板（待接口）
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 20px; }

.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.page-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--color-text-dark); }
.page-desc { font-size: 13px; color: var(--color-text-medium); margin: 0; }
.page-head-actions { display: flex; gap: 10px; }

.error-banner {
  margin-bottom: 12px;
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

.primary-btn, .secondary-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 10px 18px; border-radius: 10px; font-size: 14px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}
.primary-btn { border: 0; background: var(--gradient-primary); color: #fff; }
.primary-btn.block { width: 100%; padding: 9px 14px; font-size: 13px; border-radius: 8px; }
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }
.primary-btn.is-loading { opacity: .75; pointer-events: none; }
.secondary-btn { border: 1px solid var(--color-primary-border); background: #fff; color: var(--color-primary); }
.secondary-btn.block { width: 100%; padding: 8px 14px; font-size: 13px; border-radius: 8px; }
.secondary-btn:disabled { opacity: .45; cursor: not-allowed; }
.secondary-btn:hover:not(:disabled) { background: var(--color-primary-light); }

.upload-label { cursor: pointer; }

.card { background: #fff; border: 1px solid var(--color-border, #eae7f0); border-radius: 14px; padding: 18px 20px; }

.hint { padding: 32px; text-align: center; color: var(--color-text-medium); font-size: 14px; }
.hint.empty code { background: var(--color-primary-light); color: var(--color-primary); padding: 2px 6px; border-radius: 4px; font-size: 12px; margin: 0 2px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }

.tpl-card {
  border: 1px solid var(--color-primary-border);
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #fff;
  transition: box-shadow 0.18s, border-color 0.18s;
}
.tpl-card:hover {
  border-color: var(--color-primary-border-strong);
  box-shadow: 0 6px 14px rgba(123, 63, 178, 0.08);
}

.tpl-head { display: flex; flex-direction: column; gap: 4px; min-height: 0; }
.tpl-title { font-size: 15px; font-weight: 600; color: var(--color-text-dark); line-height: 1.35; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.tpl-file { font-size: 12px; color: var(--color-text-light); font-family: 'JetBrains Mono', Consolas, monospace; }

.tpl-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: var(--color-text-medium); }

.tpl-outline {
  border: 1px solid var(--color-border);
  border-radius: 9px;
  padding: 10px 12px;
  background: #fdfcff;
}
.outline-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-medium);
  margin-bottom: 8px;
}
.outline-empty { padding: 2px 0; }
.outline-tree {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}
.outline-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--color-text-dark);
  line-height: 1.45;
}
.outline-level {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--color-primary);
  background: var(--color-primary-light);
  padding: 1px 6px;
  border-radius: 4px;
}
.outline-order {
  color: var(--color-text-light);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  min-width: 22px;
  flex-shrink: 0;
}
.outline-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tpl-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
}

.muted {
  font-size: 12px;
  color: var(--color-text-light);
}
</style>
