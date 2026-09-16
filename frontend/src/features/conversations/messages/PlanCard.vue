<script setup lang="ts">
import { computed } from 'vue'
import type { Message, PlanMessagePayload } from '../../../types'

const props = defineProps<{ message: Message; suggestable: boolean }>()
const emit = defineEmits<{ (e: 'suggest', text: string): void }>()

const plan = computed(() => (props.message.payload as unknown as PlanMessagePayload).plan)

const dimensions = computed(() => Object.entries(plan.value?.global_context?.dimensions || {}))

const SUGGESTIONS = ['确认，开始生成', '去掉最后一个章节', '报告期间改成 2025 上半年']
</script>

<template>
  <div class="plan-card">
    <div class="plan-head">
      <span class="plan-title">{{ plan?.title }}</span>
      <span class="plan-version">v{{ plan?.version }}</span>
    </div>

    <div class="plan-context">
      <div class="plan-field">
        <span class="plan-field-label">报告期间</span>
        <span class="plan-field-value">{{ plan?.global_context?.report_period || '未指定' }}</span>
      </div>
      <div v-for="[key, value] in dimensions" :key="key" class="plan-field">
        <span class="plan-field-label">{{ key }}</span>
        <span class="plan-field-value">{{ value }}</span>
      </div>
    </div>

    <ol class="plan-chapters">
      <li v-for="chapter in plan?.chapters || []" :key="chapter.section_id" class="plan-chapter">
        <div class="plan-chapter-title">{{ chapter.title }}</div>
        <div v-if="chapter.metrics.length" class="plan-metrics">
          <span v-for="metric in chapter.metrics" :key="metric" class="plan-metric">{{ metric }}</span>
        </div>
        <div v-else class="plan-metrics-empty">未指定指标</div>
        <ul v-if="chapter.subsections?.length" class="plan-subsections">
          <li
            v-for="sub in chapter.subsections"
            :key="sub.section_id"
            class="plan-subsection"
            :style="{ paddingLeft: `${Math.max(0, sub.level - chapter.level - 1) * 14}px` }"
          >{{ sub.title }}</li>
        </ul>
      </li>
    </ol>

    <div v-if="suggestable" class="plan-suggestions">
      <button
        v-for="suggestion in SUGGESTIONS"
        :key="suggestion"
        type="button"
        class="plan-suggestion"
        @click="emit('suggest', suggestion)"
      >{{ suggestion }}</button>
    </div>
  </div>
</template>

<style scoped>
.plan-card {
  border: 1px solid var(--color-primary-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plan-head { display: flex; align-items: center; gap: 10px; }
.plan-title { font-size: 15px; font-weight: 600; color: var(--color-text-dark); }
.plan-version {
  font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
  background: var(--color-primary-light); color: var(--color-primary);
}

.plan-context { display: flex; flex-wrap: wrap; gap: 8px; }
.plan-field {
  display: flex; align-items: center; gap: 6px;
  background: #fbfaff; border-radius: 8px; padding: 4px 10px; font-size: 12px;
}
.plan-field-label { color: var(--color-text-light); }
.plan-field-value { color: var(--color-text-dark); font-weight: 500; }

.plan-chapters { list-style: decimal; margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 10px; }
.plan-chapter-title { font-size: 13.5px; font-weight: 600; color: var(--color-text-dark); }
.plan-metrics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.plan-metric {
  font-size: 11.5px; padding: 2px 8px; border-radius: 6px;
  background: var(--color-primary-light); color: var(--color-primary);
}
.plan-metrics-empty { font-size: 11.5px; color: var(--color-text-light); margin-top: 5px; }

.plan-subsections {
  list-style: none;
  margin: 8px 0 0;
  padding: 0 0 0 10px;
  border-left: 2px solid var(--color-primary-border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plan-subsection { font-size: 12.5px; color: var(--color-text-medium); line-height: 1.5; }

.plan-suggestions { display: flex; flex-wrap: wrap; gap: 8px; padding-top: 4px; }
.plan-suggestion {
  font-size: 12.5px; padding: 6px 12px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--color-primary-border); background: #fff; color: var(--color-primary);
  font-family: inherit;
}
.plan-suggestion:hover { background: var(--color-primary-light); }
</style>
