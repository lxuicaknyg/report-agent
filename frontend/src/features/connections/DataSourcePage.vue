<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useConnectionStore } from '../../stores/connection'
import type { ConnectionDriver, DataConnection, DriverSpec } from '../../types'

const store = useConnectionStore()

const showForm = ref(false)
/** The connection being edited; null means the form is creating a new one. */
const editing = ref<DataConnection | null>(null)

const form = reactive({
  name: '',
  driver: 'mysql' as ConnectionDriver,
  host: '',
  port: null as number | null,
  database: '',
  username: '',
  password: '',
  options: {} as Record<string, string>,
})
/** True once the user types in the password box of an edit form. */
const passwordTouched = ref(false)
const formError = ref<string | null>(null)

const currentSpec = computed<DriverSpec | undefined>(() => store.driverMap.get(form.driver))
const extraFields = computed(() => currentSpec.value?.extra_fields ?? [])

onMounted(async () => {
  await store.loadDrivers()
  await store.load()
})

function driverLabel(driver: ConnectionDriver): string {
  return store.driverMap.get(driver)?.label ?? driver
}

function statusText(item: DataConnection): string {
  if (item.status === 'ok') return '连接正常'
  if (item.status === 'failed') return item.last_error || '连接失败'
  return '未测试'
}

function openCreate() {
  editing.value = null
  passwordTouched.value = false
  formError.value = null
  Object.assign(form, {
    name: '',
    driver: 'mysql' as ConnectionDriver,
    host: '',
    port: null,
    database: '',
    username: '',
    password: '',
    options: {},
  })
  onDriverChange()
  showForm.value = true
}

function openEdit(item: DataConnection) {
  editing.value = item
  passwordTouched.value = false
  formError.value = null
  Object.assign(form, {
    name: item.name,
    driver: item.driver,
    host: item.host,
    port: item.port,
    database: item.database,
    username: item.username,
    // Never populated: the API does not return it. Left blank means unchanged.
    password: '',
    options: Object.fromEntries(
      Object.entries(item.options ?? {}).map(([key, value]) => [key, String(value ?? '')]),
    ),
  })
  showForm.value = true
}

/** Switching driver re-seeds the port with that driver's default. */
function onDriverChange() {
  const spec = store.driverMap.get(form.driver)
  if (!spec) return
  if (!editing.value || form.driver !== editing.value.driver) {
    form.port = spec.default_port
  }
  for (const field of spec.extra_fields ?? []) {
    if (!(field.key in form.options)) form.options[field.key] = ''
  }
}

async function submit() {
  formError.value = null
  if (!form.name.trim() || !form.host.trim()) {
    formError.value = '名称和主机地址不能为空'
    return
  }
  const payload = {
    name: form.name.trim(),
    driver: form.driver,
    host: form.host.trim(),
    port: form.port,
    database: form.database.trim(),
    username: form.username.trim(),
    // Omitting the field entirely is how the backend is told to keep the
    // stored secret; sending '' would clear it.
    ...(editing.value && !passwordTouched.value ? {} : { password: form.password }),
    options: Object.fromEntries(
      extraFields.value
        .map((field) => [field.key, (form.options[field.key] ?? '').trim()])
        .filter(([, value]) => value !== ''),
    ),
  }
  const ok = editing.value
    ? await store.update(editing.value.connection_id, payload)
    : await store.create(payload)
  if (ok) {
    showForm.value = false
  } else {
    formError.value = store.error
  }
}

async function handleTest(item: DataConnection) {
  await store.test(item.connection_id)
}

async function handleDelete(item: DataConnection) {
  if (!window.confirm(`确定删除数据源「${item.name}」吗？此操作不可撤销。`)) return
  await store.remove(item.connection_id)
}
</script>

<template>
  <div class="ds-page">
    <header class="ds-head">
      <div>
        <h1 class="ds-title">数据源</h1>
        <p class="ds-sub">配置报告取数可用的数据库。补充指标时可以选择这里的数据源并编写 SQL。</p>
      </div>
      <button type="button" class="primary-btn" @click="openCreate">新建数据源</button>
    </header>

    <div v-if="store.error && !showForm" class="banner error">
      {{ store.error }}
      <button type="button" class="banner-close" @click="store.clearError()">关闭</button>
    </div>

    <div v-if="store.isLoading" class="ds-empty">加载中…</div>

    <div v-else-if="store.connections.length === 0" class="ds-empty">
      <p>还没有配置数据源。</p>
      <p class="ds-empty-hint">支持 MySQL、GaussDB、openLooKeng。</p>
    </div>

    <ul v-else class="ds-list">
      <li v-for="item in store.connections" :key="item.connection_id" class="ds-card">
        <div class="ds-card-main">
          <div class="ds-card-head">
            <span class="ds-name">{{ item.name }}</span>
            <span class="ds-driver">{{ driverLabel(item.driver) }}</span>
            <span class="ds-status" :class="item.status">{{ statusText(item) }}</span>
          </div>
          <div class="ds-meta">
            <code>{{ item.host }}:{{ item.port }}</code>
            <span v-if="item.database">· {{ item.database }}</span>
            <span v-if="item.username">· {{ item.username }}</span>
            <span v-if="!item.has_password" class="ds-warn">· 未设置密码</span>
          </div>
          <p
            v-if="store.testResults[item.connection_id]"
            class="ds-test"
            :class="{ ok: store.testResults[item.connection_id].success }"
          >
            {{ store.testResults[item.connection_id].message }}
            （{{ store.testResults[item.connection_id].elapsed_ms }} ms）
            <span v-if="store.testResults[item.connection_id].server_version">
              · {{ store.testResults[item.connection_id].server_version }}
            </span>
          </p>
        </div>
        <div class="ds-actions">
          <button
            type="button"
            class="mini-btn"
            :disabled="store.testingId === item.connection_id"
            @click="handleTest(item)"
          >
            {{ store.testingId === item.connection_id ? '测试中…' : '测试连接' }}
          </button>
          <button type="button" class="mini-btn" @click="openEdit(item)">编辑</button>
          <button type="button" class="mini-btn danger" @click="handleDelete(item)">删除</button>
        </div>
      </li>
    </ul>

    <div v-if="showForm" class="ds-modal-mask" @click.self="showForm = false">
      <div class="ds-modal" role="dialog" aria-modal="true">
        <h2 class="ds-modal-title">{{ editing ? '编辑数据源' : '新建数据源' }}</h2>

        <div class="field">
          <label>名称</label>
          <input v-model="form.name" type="text" placeholder="例如：风控只读库" />
        </div>

        <div class="field">
          <label>类型</label>
          <select v-model="form.driver" @change="onDriverChange">
            <option v-for="spec in store.drivers" :key="spec.driver" :value="spec.driver">
              {{ spec.label }}
            </option>
          </select>
          <p v-if="currentSpec?.note" class="field-hint">{{ currentSpec.note }}</p>
          <p v-if="currentSpec" class="field-hint dim">依赖：{{ currentSpec.driver_package }}</p>
        </div>

        <div class="field-row">
          <div class="field grow">
            <label>主机</label>
            <input v-model="form.host" type="text" placeholder="10.0.0.9 或 db.internal" />
          </div>
          <div class="field port">
            <label>端口</label>
            <input v-model.number="form.port" type="number" :placeholder="String(currentSpec?.default_port ?? '')" />
          </div>
        </div>

        <div v-if="currentSpec?.requires_database" class="field">
          <label>数据库</label>
          <input v-model="form.database" type="text" placeholder="risk" />
        </div>

        <div class="field-row">
          <div class="field grow">
            <label>用户名</label>
            <input v-model="form.username" type="text" autocomplete="off" />
          </div>
          <div class="field grow">
            <label>密码</label>
            <input
              v-model="form.password"
              type="password"
              autocomplete="new-password"
              :placeholder="editing && editing.has_password ? '留空表示不修改' : ''"
              @input="passwordTouched = true"
            />
          </div>
        </div>

        <div v-for="field in extraFields" :key="field.key" class="field">
          <label>{{ field.label }}<span v-if="field.required" class="req">*</span></label>
          <input v-model="form.options[field.key]" type="text" :placeholder="field.placeholder" />
        </div>

        <p v-if="formError" class="form-error">{{ formError }}</p>

        <div class="ds-modal-actions">
          <button type="button" class="mini-btn" @click="showForm = false">取消</button>
          <button type="button" class="primary-btn" :disabled="store.isSaving" @click="submit">
            {{ store.isSaving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ds-page { padding: 28px 32px; max-width: 940px; margin: 0 auto; overflow-y: auto; height: 100%; }

.ds-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.ds-title { margin: 0 0 6px; font-size: 20px; color: var(--color-text-dark); }
.ds-sub { margin: 0; font-size: 13px; color: var(--color-text-light); }

.primary-btn {
  flex-shrink: 0; padding: 9px 18px; border: 0; border-radius: var(--radius-pill);
  background: var(--gradient-primary); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
}
.primary-btn:disabled { opacity: .5; cursor: not-allowed; }

.banner { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; border-radius: var(--radius-lg); font-size: 13px; margin-bottom: 16px; }
.banner.error { background: var(--color-error-bg); border: 1px solid var(--color-error-border); color: var(--color-error); }
.banner-close { border: 0; background: transparent; color: inherit; cursor: pointer; font-size: 12px; }

.ds-empty { padding: 48px 0; text-align: center; color: var(--color-text-light); font-size: 14px; }
.ds-empty-hint { font-size: 12px; color: var(--color-text-lighter); }

.ds-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.ds-card {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  padding: 16px 18px; background: var(--color-bg-card);
  border: 1px solid var(--color-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-card);
}
.ds-card-main { min-width: 0; }
.ds-card-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.ds-name { font-size: 15px; font-weight: 600; color: var(--color-text-dark); }
.ds-driver {
  padding: 2px 8px; border-radius: var(--radius-pill); font-size: 11px;
  background: var(--color-primary-light); color: var(--color-primary); border: 1px solid var(--color-primary-border);
}
.ds-status { padding: 2px 8px; border-radius: var(--radius-pill); font-size: 11px; }
.ds-status.ok { background: var(--color-success-bg); color: var(--color-success); }
.ds-status.failed { background: var(--color-error-bg); color: var(--color-error); }
.ds-status.untested { background: var(--color-bg-gray); color: var(--color-text-light); }

.ds-meta { font-size: 12px; color: var(--color-text-light); display: flex; gap: 6px; flex-wrap: wrap; }
.ds-meta code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.ds-warn { color: var(--color-warning); }
.ds-test { margin: 8px 0 0; font-size: 12px; color: var(--color-error); }
.ds-test.ok { color: var(--color-success); }

.ds-actions { display: flex; gap: 6px; flex-shrink: 0; }
.mini-btn {
  padding: 5px 12px; border: 1px solid var(--color-border); border-radius: var(--radius-pill);
  background: #fff; color: var(--color-text-body); font-size: 12px; cursor: pointer;
}
.mini-btn:hover:not(:disabled) { border-color: var(--color-primary-border-strong); color: var(--color-primary); }
.mini-btn:disabled { opacity: .5; cursor: not-allowed; }
.mini-btn.danger:hover { border-color: var(--color-error-border); color: var(--color-error); }

.ds-modal-mask {
  position: fixed; inset: 0; background: rgba(36, 24, 56, 0.35);
  display: flex; align-items: center; justify-content: center; padding: 24px; z-index: 50;
}
.ds-modal {
  width: 100%; max-width: 520px; max-height: 88vh; overflow-y: auto;
  background: var(--color-bg-card); border-radius: 14px; padding: 24px; box-shadow: var(--shadow-dropdown);
}
.ds-modal-title { margin: 0 0 18px; font-size: 17px; color: var(--color-text-dark); }

.field { margin-bottom: 14px; }
.field-row { display: flex; gap: 12px; }
.field.grow { flex: 1; min-width: 0; }
.field.port { width: 110px; flex-shrink: 0; }
.field label { display: block; margin-bottom: 5px; font-size: 12px; font-weight: 600; color: var(--color-text-medium); }
.req { color: var(--color-error); margin-left: 2px; }
.field input, .field select {
  width: 100%; height: 34px; padding: 0 10px; font-size: 13px;
  border: 1px solid var(--color-border); border-radius: var(--radius-md);
  background: #fff; color: var(--color-text-body);
}
.field input:focus, .field select:focus { outline: none; border-color: var(--color-primary); }
.field-hint { margin: 5px 0 0; font-size: 11px; color: var(--color-text-light); }
.field-hint.dim { color: var(--color-text-lighter); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }

.form-error {
  margin: 0 0 12px; padding: 8px 12px; font-size: 12px;
  background: var(--color-error-bg); border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md); color: var(--color-error);
}
.ds-modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
</style>
