<script setup lang="ts">
import { computed } from 'vue'
import type { PlanResponse, Task } from '../../types'
import StepTimeline from './StepTimeline.vue'

const props = defineProps<{
  plan: PlanResponse | null
  task: Task | null
}>()

const emit = defineEmits<{
  (e: 'confirm', stepIds?: string[]): void
  (e: 'retry', stepId: string): void
  (e: 'skip', stepId: string): void
  (e: 'cancel'): void
  (e: 'pause'): void
  (e: 'resume'): void
}>()

const steps = computed(() => props.plan?.steps ?? [])

const waitingSteps = computed(() =>
  steps.value.filter((s) => s.status === 'pending' || s.status === 'needs_data')
)

const hasActiveTask = computed(() =>
  props.task && ['created', 'planning', 'running', 'needs_data'].includes(props.task.status)
)

const canPause = computed(() => props.task?.status === 'running')
const canResume = computed(() => false)
const canCancel = computed(() => hasActiveTask.value)

function handleConfirmAll() {
  const ids = waitingSteps.value.map((s) => s.id)
  emit('confirm', ids.length > 0 ? ids : undefined)
}

function handleConfirmStep(stepId: string) {
  emit('confirm', [stepId])
}

function handleRetry(stepId: string) {
  emit('retry', stepId)
}

function handleSkip(stepId: string) {
  emit('skip', stepId)
}
</script>

<template>
  <div class="plan-panel">
    <div v-if="!plan" class="empty-state">
      <div class="empty-icon">📋</div>
      <h3>暂无执行计划</h3>
      <p>发送需求后，系统将自动生成执行计划</p>
    </div>

    <template v-else>
      <div class="plan-goal">
        <div class="goal-header">
          <span class="goal-label">任务目标</span>
          <span class="plan-version">v{{ plan.version }}</span>
        </div>
        <p class="goal-text">{{ plan.summary }}</p>
      </div>

      <div v-if="waitingSteps.length > 0" class="confirm-section">
        <div class="section-title">
          <span>⏳ 等待确认</span>
          <button class="confirm-all-btn" @click="handleConfirmAll">
            全部确认
          </button>
        </div>
        <div
          v-for="step in waitingSteps"
          :key="step.id"
          class="confirm-item"
        >
          <div class="confirm-info">
            <div class="confirm-tool">{{ step.tool_name ?? step.agent_name ?? 'agent' }}</div>
            <div class="confirm-desc">{{ step.title }}</div>
          </div>
          <div class="confirm-actions">
            <button class="btn-confirm" @click="handleConfirmStep(step.id)">✓ 确认</button>
          </div>
        </div>
      </div>

      <div class="timeline-section">
        <div class="section-title">执行时间线</div>
        <StepTimeline :steps="steps" />
      </div>

      <div v-if="hasActiveTask" class="task-actions">
        <button v-if="canPause" class="action-btn pause" @click="emit('pause')">
          ⏸ 暂停任务
        </button>
        <button v-if="canResume" class="action-btn resume" @click="emit('resume')">
          ▶ 继续任务
        </button>
        <button v-if="canCancel" class="action-btn cancel" @click="emit('cancel')">
          ✕ 取消任务
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.plan-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  height: 100%;
  color: var(--color-text-light);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--color-text-dark);
}

.empty-state p {
  margin: 0;
  font-size: 13px;
}

.plan-goal {
  padding: 12px 14px;
  background: var(--color-primary-light);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-primary-border);
}

.goal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.goal-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary);
}

.plan-version {
  font-size: 11px;
  color: var(--color-primary-accent);
  background: rgba(255, 255, 255, 0.6);
  padding: 2px 8px;
  border-radius: var(--radius-pill);
}

.goal-text {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-dark);
  line-height: 1.5;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-medium);
  margin-bottom: 10px;
}

.timeline-section {
  display: flex;
  flex-direction: column;
}

.confirm-section {
  background: var(--color-warning-bg, #fff7ed);
  border-radius: var(--radius-md);
  padding: 12px;
  border: 1px solid var(--color-warning, #d97706);
}

.confirm-all-btn {
  padding: 4px 12px;
  background: var(--gradient-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: box-shadow 0.15s ease, transform 0.05s ease;
}

.confirm-all-btn:hover {
  box-shadow: 0 4px 12px rgba(123, 63, 178, 0.25);
}

.confirm-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px;
  background: var(--color-bg-card, #fff);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-card, 0 1px 2px rgba(16, 42, 67, 0.06));
  margin-bottom: 8px;
}

.confirm-item:last-child {
  margin-bottom: 0;
}

.confirm-info {
  flex: 1;
}

.confirm-tool {
  font-family: monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary);
  margin-bottom: 2px;
}

.confirm-desc {
  font-size: 13px;
  color: var(--color-text-medium);
  margin-bottom: 4px;
}

.confirm-actions {
  flex-shrink: 0;
}

.btn-confirm {
  padding: 6px 14px;
  background: var(--gradient-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: box-shadow 0.15s ease, transform 0.05s ease;
}

.btn-confirm:hover {
  box-shadow: 0 4px 12px rgba(123, 63, 178, 0.25);
}

.task-actions {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--color-primary-border);
}

.action-btn {
  flex: 1;
  padding: 10px 12px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn.pause {
  background: var(--color-warning-bg, #fff7ed);
  color: var(--color-warning, #d97706);
  border: 1px solid var(--color-warning, #d97706);
}

.action-btn.pause:hover {
  filter: brightness(0.97);
}

.action-btn.resume {
  background: var(--color-primary-light);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border-strong);
}

.action-btn.cancel {
  background: var(--color-error-bg, #fef2f2);
  color: var(--color-error, #dc2626);
  border: 1px solid var(--color-error-border, #fecaca);
}

.action-btn.cancel:hover {
  filter: brightness(0.97);
}
</style>
