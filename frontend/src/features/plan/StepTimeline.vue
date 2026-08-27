<script setup lang="ts">
import { computed } from 'vue'
import type { PlanStepResponse } from '../../types'

const props = defineProps<{
  steps: PlanStepResponse[]
}>()

const sortedSteps = computed(() => {
  const order = ['pending', 'queued', 'running', 'completed', 'failed', 'skipped', 'cancelled', 'needs_data']
  return [...props.steps].sort(
    (a, b) => order.indexOf(a.status) - order.indexOf(b.status)
  )
})

function statusClass(status: string): string {
  return `status-${status}`
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '等待中',
    queued: '队列中',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过',
    cancelled: '已取消',
    needs_data: '等待数据',
  }
  return map[status] ?? status
}
</script>

<template>
  <div class="step-timeline">
    <div
      v-for="(step, idx) in sortedSteps"
      :key="step.id"
      class="step-item"
      :class="statusClass(step.status)"
    >
      <div class="step-connector">
        <div class="step-icon">
          <!-- pending -->
          <svg v-if="step.status === 'pending' || step.status === 'queued'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="6" />
          </svg>
          <!-- running -->
          <svg v-else-if="step.status === 'running' || step.status === 'needs_data'" class="spin-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
          </svg>
          <!-- completed -->
          <svg v-else-if="step.status === 'completed'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          <!-- failed -->
          <svg v-else-if="step.status === 'failed'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          <!-- skipped / cancelled -->
          <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="19" y1="12" x2="5" y2="12" />
          </svg>
        </div>
        <div v-if="idx < sortedSteps.length - 1" class="connector-line"></div>
      </div>

      <div class="step-content">
        <div class="step-header">
          <div class="step-title">{{ step.title }}</div>
          <div class="step-status-label">{{ statusLabel(step.status) }}</div>
        </div>

        <div class="step-info">
          <div class="step-tool">
            <span class="tool-label">工具：</span>
            <span class="tool-name">{{ step.tool_name ?? step.agent_name ?? '—' }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="steps.length === 0" class="no-steps">
      暂无步骤信息
    </div>
  </div>
</template>

<style scoped>
.step-timeline {
  display: flex;
  flex-direction: column;
}

.step-item {
  display: flex;
  gap: 12px;
  position: relative;
}

.step-item + .step-item {
  margin-top: 4px;
}

.step-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 28px;
  flex-shrink: 0;
}

.step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  background: var(--color-primary-light);
  color: var(--color-text-lighter);
  flex-shrink: 0;
  z-index: 1;
}

.status-completed .step-icon {
  background: var(--color-success);
  color: #fff;
}

.status-running .step-icon,
.status-needs_data .step-icon {
  background: var(--color-primary);
  color: #fff;
}

.status-running .spin-icon,
.status-needs_data .spin-icon {
  animation: spin 1.5s linear infinite;
}

.status-pending .step-icon,
.status-queued .step-icon {
  background: var(--color-primary-light);
  color: var(--color-text-lighter);
}

.status-failed .step-icon {
  background: var(--color-error);
  color: #fff;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.connector-line {
  width: 2px;
  flex: 1;
  min-height: 24px;
  background: var(--color-primary-border);
  margin: 4px 0;
}

.step-item.status-completed .connector-line {
  background: var(--color-success);
}

.step-content {
  flex: 1;
  padding-bottom: 16px;
  min-width: 0;
}

.step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.step-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-dark);
}

.step-status-label {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--color-primary-light);
  color: var(--color-text-lighter);
}

.status-completed .step-status-label {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-running .step-status-label,
.status-needs_data .step-status-label {
  background: var(--color-primary-light);
  color: var(--color-primary-accent);
}

.status-failed .step-status-label {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.step-info {
  font-size: 12px;
  color: var(--color-text-light);
}

.step-tool {
  margin-bottom: 4px;
}

.tool-label {
  color: var(--color-text-lighter);
}

.tool-name {
  font-family: monospace;
  color: var(--color-primary);
}

.no-steps {
  padding: 20px;
  text-align: center;
  color: var(--color-text-lighter);
  font-size: 13px;
}
</style>
