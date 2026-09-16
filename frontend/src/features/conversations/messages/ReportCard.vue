<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Message, ReportArtifact, ReportMessagePayload } from '../../../types'
import { reportApi } from '../../../services/api/reports'
import { downloadBlob } from '../../../utils/download'

const props = defineProps<{ message: Message }>()

const payload = computed(() => props.message.payload as unknown as ReportMessagePayload)
const artifacts = computed(() => payload.value.artifacts || [])
const downloadError = ref('')

async function download(artifact: ReportArtifact) {
  downloadError.value = ''
  const result = await reportApi.downloadArtifact(payload.value.session_id, artifact.artifact_id)
  if (result.success && result.data) downloadBlob(result.data, artifact.name)
  else downloadError.value = result.error?.message || '下载失败，请重试'
}
</script>

<template>
  <div class="report-card">
    <div class="report-actions">
      <button
        v-for="artifact in artifacts"
        :key="artifact.artifact_id"
        type="button"
        class="report-btn"
        @click="download(artifact)"
      >下载 {{ artifact.format.toUpperCase() }}</button>
    </div>
    <p v-if="downloadError" class="report-error">{{ downloadError }}</p>
  </div>
</template>

<style scoped>
.report-card { display: flex; flex-direction: column; gap: 8px; }
.report-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.report-btn {
  font-size: 12.5px; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-family: inherit;
  font-weight: 600; border: 0; background: var(--gradient-primary); color: #fff;
  transition: box-shadow 0.15s ease;
}
.report-btn:hover { box-shadow: 0 4px 14px rgba(123, 63, 178, 0.28); }
.report-error { margin: 0; font-size: 12px; color: #b91c1c; }
</style>
