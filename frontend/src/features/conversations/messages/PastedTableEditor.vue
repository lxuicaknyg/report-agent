<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { supplementApi } from '../../../services/api'
import type { ParsedTable } from '../../../types'

const props = defineProps<{
  /** What the rows will be recorded as, shown so the paste can be checked
   * against the thing that was actually asked for. */
  metric: string
  text: string
}>()

const emit = defineEmits<{
  (e: 'update:text', value: string): void
  /** The parse the card should submit against, or null while there is none. */
  (e: 'parsed', value: ParsedTable | null): void
}>()

const parsed = ref<ParsedTable | null>(null)
const failure = ref('')
const checking = ref(false)

/** Which text `parsed` describes, so an edit invalidates it rather than
 * letting a preview of the previous paste stand in for the current one. */
const parsedFor = ref<string | null>(null)

const PLACEHOLDER = `直接从 Excel 复制粘贴，或者每行写一个指标：

不良贷款余额：52,501,109.06 元
不良率：1.28%
拨备覆盖率：320%`

const fresh = computed(() => parsed.value !== null && parsedFor.value === props.text)

/**
 * Parse on the server, after the typing stops.
 *
 * The browser never reads the text itself: what the user approves here has to
 * be the same parse that lands in the report, and two implementations of
 * "this looks like a table" would eventually disagree about someone's data.
 */
let timer: ReturnType<typeof setTimeout> | undefined
watch(
  () => props.text,
  (text) => {
    clearTimeout(timer)
    parsed.value = null
    parsedFor.value = null
    failure.value = ''
    emit('parsed', null)
    if (!text.trim()) return
    checking.value = true
    timer = setTimeout(() => check(text), 400)
  },
  { immediate: true },
)

async function check(text: string) {
  const result = await supplementApi.previewTable(text)
  // The user may have kept typing; a late answer about older text is not an
  // answer about what is on screen now.
  if (text !== props.text) return
  checking.value = false
  if (!result.success || !result.data) {
    failure.value = result.error?.message || '这段内容读不成表格'
    return
  }
  parsed.value = result.data
  parsedFor.value = text
  emit('parsed', result.data)
}

const previewRows = computed(() => parsed.value?.rows.slice(0, 8) ?? [])
</script>

<template>
  <div class="paste">
    <label class="paste-field">
      <span class="paste-label">
        明细数据
        <span class="paste-hint">第一行当作表头；支持 Excel 复制、Markdown 表格、逗号分隔</span>
      </span>
      <textarea
        class="paste-input"
        :value="text"
        rows="5"
        spellcheck="false"
        :placeholder="PLACEHOLDER"
        @input="emit('update:text', ($event.target as HTMLTextAreaElement).value)"
      />
    </label>

    <p v-if="checking" class="paste-note">正在识别…</p>
    <p v-else-if="failure" class="paste-failure">{{ failure }}</p>

    <template v-if="fresh && parsed">
      <div class="paste-preview">
        <div class="paste-table-wrap">
          <table class="paste-table">
            <thead>
              <tr>
                <th v-for="column in parsed.columns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in previewRows" :key="index">
                <td v-for="column in parsed.columns" :key="column">{{ row[column] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="parsed.row_count > previewRows.length" class="paste-more">
          共 {{ parsed.row_count }} 行，仅显示前 {{ previewRows.length }} 行
        </p>
      </div>

      <div class="paste-reading">
        <span class="paste-reading-label">将记录为</span>
        <span class="paste-reading-body">
          <strong>{{ metric }}</strong> 明细表 · {{ parsed.row_count }} 行 ×
          {{ parsed.columns.length }} 列
          <span class="paste-dim">按「{{ parsed.format }}」读取</span>
        </span>
      </div>

      <p v-for="warning in parsed.warnings" :key="warning" class="paste-warn">{{ warning }}</p>
    </template>
  </div>
</template>

<style scoped>
.paste {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 2px;
  min-width: 0;
}

.paste-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.paste-label {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-light);
}

.paste-hint {
  font-weight: 500;
  color: var(--color-text-lighter);
}

.paste-input {
  width: 100%;
  padding: 7px 11px;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
  background: #fff;
  color: var(--color-text-dark);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  outline: none;
  resize: vertical;
  min-height: 92px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.paste-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-light);
}

.paste-input::placeholder {
  color: var(--color-text-lighter);
}

.paste-note {
  margin: 0;
  font-size: 11.5px;
  color: var(--color-text-light);
}

.paste-failure {
  margin: 0;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 11.5px;
  line-height: 1.55;
}

.paste-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.paste-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-primary-border);
  border-radius: 8px;
}

.paste-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.paste-table th,
.paste-table td {
  padding: 6px 10px;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--color-primary-border);
}

.paste-table tbody tr:last-child td {
  border-bottom: 0;
}

.paste-table th {
  background: var(--color-bg-gray);
  font-weight: 600;
  color: var(--color-text-medium);
}

.paste-more {
  margin: 0;
  font-size: 11px;
  color: var(--color-text-lighter);
}

.paste-reading {
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

.paste-reading-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
}

.paste-reading-body {
  min-width: 0;
  word-break: break-word;
}

.paste-dim {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.65);
  font-size: 11.5px;
}

.paste-warn {
  margin: 0;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: 11.5px;
  line-height: 1.6;
}
</style>
