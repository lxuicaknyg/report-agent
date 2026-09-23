<script setup lang="ts">
/**
 * 模块的落地页。
 *
 * 点进工具后页面上只有「顶栏 + 这里」—— 报告工作台的会话侧栏是它专有的，
 * 不会出现在你的页面上，所以整个内容区都归你。
 */
import { onMounted, ref } from 'vue'

import { useAuthStore } from '../../../stores'
import { useExampleStore } from '../stores/example'

const store = useExampleStore()
// 当前登录用户，只读。登录和登出由宿主负责，模块不要调 login() / logout()。
const auth = useAuthStore()

const draftName = ref('')

onMounted(() => {
  void store.refresh()
})

async function submit() {
  if (!draftName.value.trim()) return
  if (await store.create(draftName.value)) draftName.value = ''
}
</script>

<template>
  <section class="example">
    <header class="head">
      <h1>示例工具</h1>
      <p class="sub">当前用户：{{ auth.username ?? '未登录' }}</p>
    </header>

    <!-- 失败要让用户看见，而不是只 console.error 一下然后界面一片空白 -->
    <p v-if="store.error" class="error" role="alert">{{ store.error }}</p>

    <div class="toolbar">
      <input
        v-model="draftName"
        class="field"
        placeholder="新建条目名称"
        @keyup.enter="submit"
      />
      <button class="btn" :disabled="!draftName.trim()" @click="submit">新建</button>
      <input
        :value="store.query"
        class="field"
        placeholder="筛选"
        @input="store.setQuery(($event.target as HTMLInputElement).value)"
      />
    </div>

    <p v-if="store.loading" class="muted">加载中…</p>
    <p v-else-if="!store.visible.length" class="muted">暂无数据。</p>
    <ul v-else class="list">
      <li v-for="item in store.visible" :key="item.item_id" class="row">
        <span class="name">{{ item.name }}</span>
        <span class="badge" :data-status="item.status">{{ item.status }}</span>
      </li>
    </ul>
  </section>
</template>

<!--
  样式必须 scoped。不要写 :root / * / html / body 这类全局规则 —— 它们会溢出
  到整个应用；尤其不要重新定义 --color-* 令牌，后加载的那份会赢，另一半界面的
  配色就废了。

  颜色、圆角、阴影一律用宿主的设计令牌，不要硬编码色值，否则宿主调整主题时
  你的页面会变成一块突兀的补丁。完整令牌清单见 CONTRIBUTING_MODULES.md 第六节。
-->
<style scoped>
.example {
  padding: 24px 32px;
  color: var(--color-text-body);
}

.head h1 {
  margin: 0;
  font-size: 20px;
  color: var(--color-text-dark);
}

.sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-light);
}

.error {
  margin: 16px 0 0;
  padding: 10px 14px;
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 13px;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin: 20px 0 16px;
}

.field {
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
  color: var(--color-text-body);
  font-size: 14px;
}

.field:focus {
  outline: none;
  border-color: var(--color-primary-border-strong);
}

.btn {
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--gradient-primary);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.row:last-child {
  border-bottom: none;
}

.row:hover {
  background: var(--color-bg-hover);
}

.badge {
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  background: var(--color-bg-gray);
  color: var(--color-text-medium);
}

.badge[data-status='ready'] {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge[data-status='failed'] {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.muted {
  color: var(--color-text-light);
  font-size: 14px;
}
</style>
