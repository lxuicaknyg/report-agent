<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDatasetStore } from '../../stores/dataset'
import { datasetApi } from '../../services/api/datasets'
import type { SqlRegisterRequest } from '../../types'

const router = useRouter()
const store = useDatasetStore()

onMounted(() => {
  void store.loadDatasets()
})

function goDetail(id: string) {
  void router.push({ name: 'dataset-detail', params: { datasetId: id } })
}

const showExcelModal = ref(false)
const excelFile = ref<File | null>(null)
const excelName = ref('')
const excelDescription = ref('')
const excelSubmitting = ref(false)
const excelError = ref<string | null>(null)
const excelFileInput = ref<HTMLInputElement | null>(null)
const successMessage = ref<string | null>(null)
const EXCEL_EXTENSIONS = ['.xlsx', '.xls']
let successTimer: ReturnType<typeof setTimeout> | null = null

function isExcelFile(file: File): boolean {
  const name = file.name.toLowerCase()
  return EXCEL_EXTENSIONS.some((ext) => name.endsWith(ext))
}

function showSuccess(msg: string) {
  successMessage.value = msg
  if (successTimer) clearTimeout(successTimer)
  successTimer = setTimeout(() => {
    successMessage.value = null
  }, 3500)
}

onUnmounted(() => {
  if (successTimer) clearTimeout(successTimer)
})

function openExcelModal() {
  excelFile.value = null
  excelName.value = ''
  excelDescription.value = ''
  excelError.value = null
  showExcelModal.value = true
}

function closeExcelModal() {
  if (excelSubmitting.value) return
  showExcelModal.value = false
}

function onExcelFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  excelError.value = null
  if (!file) {
    excelFile.value = null
    return
  }
  if (!isExcelFile(file)) {
    excelFile.value = null
    excelError.value = '仅支持 .xlsx / .xls 格式的 Excel 文件'
    input.value = ''
    return
  }
  excelFile.value = file
  if (!excelName.value) {
    excelName.value = file.name.replace(/\.xlsx?$/i, '')
  }
}

function triggerExcelFileSelect() {
  excelFileInput.value?.click()
}

function removeExcelFile(e: Event) {
  e.stopPropagation()
  excelFile.value = null
  if (excelFileInput.value) excelFileInput.value.value = ''
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function submitExcel() {
  if (!excelFile.value) {
    excelError.value = '请先选择要上传的 Excel 文件'
    return
  }
  if (!excelName.value.trim()) {
    excelError.value = '请填写数据集名称'
    return
  }
  excelSubmitting.value = true
  excelError.value = null
  let uploadedName: string | null = null
  try {
    const res = await datasetApi.uploadExcel(excelFile.value)
    if (res.success && res.data) {
      store.addDataset(res.data)
      void store.loadDatasets(true)
      uploadedName = res.data.name || excelName.value.trim()
    } else if (res.error) {
      excelError.value = res.error.message
    } else {
      excelError.value = '上传失败，未知错误'
    }
  } catch (e) {
    excelError.value = String(e)
  } finally {
    excelSubmitting.value = false
    if (uploadedName) {
      showSuccess(`数据集已上传：${uploadedName}`)
      closeExcelModal()
    }
  }
}

const showSqlModal = ref(false)
const sqlForm = ref<SqlRegisterRequest>({
  connection_url: '',
  dataset_id: '',
  table_name: '',
  description: '',
})
const sqlSubmitting = ref(false)
const sqlError = ref<string | null>(null)

function openSqlModal() {
  sqlForm.value = {
    connection_url: '',
    dataset_id: '',
    table_name: '',
    description: '',
  }
  sqlError.value = null
  showSqlModal.value = true
}

function closeSqlModal() {
  showSqlModal.value = false
}

async function submitSql() {
  if (!sqlForm.value.connection_url.trim()) {
    sqlError.value = '请填写连接地址'
    return
  }
  if (!sqlForm.value.dataset_id.trim()) {
    sqlError.value = '请填写数据集 ID'
    return
  }
  if (!sqlForm.value.table_name.trim()) {
    sqlError.value = '请填写表名'
    return
  }
  sqlSubmitting.value = true
  sqlError.value = null
  try {
    const res = await datasetApi.registerSql(sqlForm.value)
    if (res.success && res.data) {
      store.addDataset(res.data)
      void store.loadDatasets(true)
      closeSqlModal()
    } else if (res.error) {
      sqlError.value = res.error.message
    } else {
      sqlError.value = '注册失败，未知错误'
    }
  } catch (e) {
    sqlError.value = String(e)
  } finally {
    sqlSubmitting.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h2 class="page-title">数据集管理</h2>
        <p class="page-desc">注册 Excel 或 SQL 数据源，查看数据结构与样例</p>
      </div>
      <div class="page-head-actions">
        <button type="button" class="secondary-btn" @click="openExcelModal">上传 Excel</button>
        <button type="button" class="primary-btn" @click="openSqlModal">注册 SQL 数据源</button>
      </div>
    </header>

    <div v-if="successMessage" class="success-banner">{{ successMessage }}</div>

    <section class="card">
      <div v-if="store.loading" class="hint">加载中…</div>
      <div v-else-if="store.datasets.length === 0" class="hint empty">
        暂无数据集。请上传 <code>.xlsx</code> 或注册 SQL 数据源。
      </div>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>类型</th>
            <th>行数</th>
            <th>字段数</th>
            <th style="width: 200px;"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in store.datasets" :key="d.dataset_id" @click="goDetail(d.dataset_id)" class="row">
            <td>{{ d.name }}</td>
            <td>
              <span class="tag" :class="d.source_type">{{ d.source_type }}</span>
            </td>
            <td>{{ d.row_count ?? '—' }}</td>
            <td>{{ d.columns?.length ?? 0 }}</td>
            <td>
              <div class="row-actions" @click.stop>
                <button type="button" class="link-btn" @click="goDetail(d.dataset_id)">查看</button>
                <button type="button" class="link-btn link-btn-danger" disabled title="删除接口待后端抵达">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="showExcelModal" class="modal-overlay" @click.self="closeExcelModal">
      <div class="modal">
        <div class="modal-head">
          <h3 class="modal-title">上传 Excel</h3>
          <button type="button" class="modal-close" @click="closeExcelModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-block">
            <label class="form-label">选择文件</label>
            <div class="file-upload-area" @click="triggerExcelFileSelect">
              <template v-if="excelFile">
                <div class="attachment-chip" @click.stop>
                  <span class="attachment-icon excel">X</span>
                  <div class="attachment-meta">
                    <span class="attachment-name" :title="excelFile.name">{{ excelFile.name }}</span>
                    <span class="attachment-size">{{ formatFileSize(excelFile.size) }} · Excel 表格</span>
                  </div>
                  <button
                    type="button"
                    class="attachment-remove"
                    aria-label="移除附件"
                    title="移除附件"
                    @click="removeExcelFile"
                  >
                    ×
                  </button>
                </div>
              </template>
              <template v-else>
                <span class="file-placeholder">点击选择 .xlsx / .xls 文件</span>
              </template>
            </div>
            <input
              ref="excelFileInput"
              type="file"
              accept=".xlsx,.xls"
              style="display:none"
              @change="onExcelFileChange"
            />
          </div>
          <div class="form-block">
            <label class="form-label">数据集名称</label>
            <input v-model="excelName" type="text" class="text-input" placeholder="例如：银行网点经营数据" />
          </div>
          <div class="form-block">
            <label class="form-label">说明（可选）</label>
            <textarea
              v-model="excelDescription"
              class="text-input textarea-input"
              rows="3"
              placeholder="简要描述数据集的用途与来源"
            />
          </div>
          <div v-if="excelSubmitting" class="uploading-banner">
            <span class="spinner"></span>
            <span>正在上传文件，请勿关闭窗口</span>
          </div>
          <div v-if="excelError" class="error-banner">{{ excelError }}</div>
        </div>
        <div class="modal-foot">
          <button type="button" class="secondary-btn" @click="closeExcelModal" :disabled="excelSubmitting">取消</button>
          <button type="button" class="primary-btn" @click="submitExcel" :disabled="excelSubmitting">
            {{ excelSubmitting ? '上传中…' : '确认上传' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showSqlModal" class="modal-overlay" @click.self="closeSqlModal">
      <div class="modal">
        <div class="modal-head">
          <h3 class="modal-title">注册 SQL 数据源</h3>
          <button type="button" class="modal-close" @click="closeSqlModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-block">
            <label class="form-label">连接地址 connection_url</label>
            <input
              v-model="sqlForm.connection_url"
              type="text"
              class="text-input mono"
              placeholder="例如：duckdb:///path/to/local.duckdb 或 postgresql://user:pass@host:5432/db"
            />
          </div>
          <div class="form-block">
            <label class="form-label">数据集 ID dataset_id</label>
            <input
              v-model="sqlForm.dataset_id"
              type="text"
              class="text-input mono"
              placeholder="英文、数字与下划线，例如：sales_2026_q2"
            />
          </div>
          <div class="form-block">
            <label class="form-label">表名 table_name</label>
            <input
              v-model="sqlForm.table_name"
              type="text"
              class="text-input mono"
              placeholder="例如：public.sales_fact"
            />
          </div>
          <div class="form-block">
            <label class="form-label">说明（可选）</label>
            <textarea
              v-model="sqlForm.description"
              class="text-input textarea-input"
              rows="3"
              placeholder="简要描述数据源的用途与数据范围"
            />
          </div>
          <div v-if="sqlError" class="error-banner">{{ sqlError }}</div>
        </div>
        <div class="modal-foot">
          <button type="button" class="secondary-btn" @click="closeSqlModal" :disabled="sqlSubmitting">取消</button>
          <button type="button" class="primary-btn" @click="submitSql" :disabled="sqlSubmitting">
            {{ sqlSubmitting ? '注册中…' : '确认注册' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 4px;
  color: var(--color-text-dark);
}

.page-desc {
  font-size: 13px;
  color: var(--color-text-medium);
  margin: 0;
}

.page-head-actions {
  display: flex;
  gap: 10px;
}

.card {
  background: #fff;
  border: 1px solid var(--color-border, #eae7f0);
  border-radius: 14px;
  padding: 18px 20px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: var(--color-text-dark);
}

.data-table th {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-medium);
  font-weight: 600;
  font-size: 12px;
}

.data-table td {
  padding: 12px;
  border-bottom: 1px solid var(--color-border);
}

.row {
  cursor: pointer;
  transition: background 0.15s;
}

.row:hover {
  background: var(--color-primary-light);
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.tag.excel { background: var(--color-primary-light); color: var(--color-primary); }
.tag.sql { background: #eef5ff; color: #2563eb; }

.hint {
  padding: 32px;
  text-align: center;
  color: var(--color-text-medium);
  font-size: 14px;
}

.hint.empty code {
  background: var(--color-primary-light);
  color: var(--color-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.link-btn {
  border: 0;
  background: transparent;
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  padding: 0;
}

.link-btn:hover { text-decoration: underline; }

.link-btn:disabled {
  color: var(--color-text-lighter);
  cursor: not-allowed;
  text-decoration: none;
}

.link-btn-danger {
  color: var(--color-error);
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 10px;
  border: 0;
  background: var(--gradient-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.secondary-btn {
  display: inline-flex;
  align-items: center;
  padding: 9px 16px;
  border-radius: 10px;
  border: 1px solid var(--color-primary-border);
  background: #fff;
  color: var(--color-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.secondary-btn:hover { background: var(--color-primary-light); }

.secondary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(47, 22, 82, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
}

.modal {
  width: 100%;
  max-width: 540px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 50px rgba(47, 22, 82, 0.22);
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid var(--color-border);
}

.modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--color-text-dark);
}

.modal-close {
  border: 0;
  background: transparent;
  color: var(--color-text-medium);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  padding: 6px 10px;
  border-radius: 6px;
}

.modal-close:hover {
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.modal-body {
  padding: 20px 22px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-foot {
  padding: 14px 22px;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.form-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.text-input {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  background: #fff;
  color: var(--color-text-dark);
  transition: border-color 0.15s;
}

.text-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.textarea-input {
  resize: vertical;
  min-height: 70px;
}

.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12.5px;
}

.file-upload-area {
  border: 1px dashed var(--color-primary-border);
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 68px;
}

.file-upload-area:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
}

.file-placeholder {
  color: var(--color-text-medium);
  font-size: 13px;
  text-align: center;
}

.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px 6px 8px;
  border: 1px solid var(--color-primary-border);
  border-radius: 10px;
  background: var(--color-primary-light);
  max-width: 100%;
}

.attachment-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.attachment-icon.excel { background: #16803d; }

.attachment-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
  text-align: left;
}

.attachment-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-dark);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.attachment-size {
  font-size: 11.5px;
  color: var(--color-text-medium);
}

.attachment-remove {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 0;
  background: transparent;
  color: var(--color-text-medium);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.attachment-remove:hover {
  background: rgba(143, 107, 255, 0.12);
  color: var(--color-primary);
}

.error-banner {
  padding: 10px 12px;
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
  border-radius: 8px;
  font-size: 13px;
}

.uploading-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  color: var(--color-primary);
  border-radius: 8px;
  font-size: 13px;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-primary-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.success-banner {
  padding: 10px 14px;
  background: #ecfdf3;
  border: 1px solid #abefc6;
  color: #067647;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
}
</style>
