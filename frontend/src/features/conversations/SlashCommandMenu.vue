<script setup lang="ts">
export type SlashCommandItem = {
  id: string
  title: string
  description: string
  template: string
  icon: 'report' | 'polish'
}

defineProps<{
  items: SlashCommandItem[]
  activeIndex: number
}>()

const emit = defineEmits<{
  (e: 'pick', item: SlashCommandItem): void
}>()
</script>

<template>
  <div class="slash-menu">
    <div class="slash-list">
      <div
        v-for="(item, idx) in items"
        :key="item.id"
        class="slash-item"
        :class="{ active: idx === activeIndex }"
        @mousedown.prevent="emit('pick', item)"
      >
        <div class="slash-icon" :class="item.icon" aria-hidden="true">
          <svg v-if="item.icon === 'report'" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="8" y1="13" x2="16" y2="13" />
            <line x1="8" y1="17" x2="14" y2="17" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
        </div>
        <div class="slash-text">
          <div class="slash-title">{{ item.title }}</div>
          <div class="slash-desc">{{ item.description }}</div>
        </div>
      </div>
      <div v-if="items.length === 0" class="slash-empty">没有匹配的命令</div>
    </div>
  </div>
</template>

<style scoped>
.slash-menu {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: calc(100% + 10px);
  background: #ffffff;
  border: 1px solid var(--color-border-soft, #e6e2ee);
  border-radius: 14px;
  box-shadow: 0 14px 40px rgba(67, 41, 120, 0.14), 0 2px 6px rgba(67, 41, 120, 0.06);
  overflow: hidden;
  z-index: 50;
}

.slash-list {
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
}

.slash-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s ease;
}

.slash-item + .slash-item {
  margin-top: 2px;
}

.slash-item:hover,
.slash-item.active {
  background: var(--color-primary-light, #f0ecf9);
}

.slash-icon {
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: var(--color-primary, #6a3dbf);
  background: var(--color-primary-light, #f0ecf9);
}

.slash-icon.polish {
  color: #b4651b;
  background: #fdf1dd;
}

.slash-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.slash-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-dark, #1a1530);
  line-height: 1.3;
}

.slash-desc {
  font-size: 12.5px;
  color: var(--color-text-light, #6b6880);
  line-height: 1.4;
}

.slash-empty {
  padding: 14px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--color-text-light, #6b6880);
}
</style>
