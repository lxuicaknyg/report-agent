<script setup lang="ts">
/**
 * Stand-in for a tool whose team has not merged its pages yet.
 *
 * The menu entry is real from day one so the shape of the workspace is fixed
 * and the route can be linked to; this page is what sits behind it until the
 * owning team replaces `component` in their module's `index.ts`.
 */
defineProps<{
  /** Tool name, as it reads in the top bar. */
  name: string
  /** Directory the owning team works in. */
  dir: string
  /** Who to ask about it. */
  owner?: string
}>()
</script>

<template>
  <section class="pending">
    <div class="card">
      <h1>{{ name }}</h1>
      <p class="lead">该工具尚未接入。</p>
      <p class="hint">
        代码放在 <code>{{ dir }}</code> 下<template v-if="owner">，由 {{ owner }} 负责</template
        >，接入方式见 <code>CONTRIBUTING_MODULES.md</code>。
      </p>
    </div>
  </section>
</template>

<style scoped>
.pending {
  display: flex;
  justify-content: center;
  padding: 64px 24px;
}

.card {
  max-width: 520px;
  padding: 32px 36px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  text-align: center;
}

h1 {
  margin: 0 0 12px;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.lead {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--color-text-medium);
}

.hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-light);
}

code {
  padding: 1px 5px;
  font-size: 12px;
  background: var(--color-bg-gray);
  border-radius: var(--radius-sm);
  color: var(--color-text-body);
}
</style>
