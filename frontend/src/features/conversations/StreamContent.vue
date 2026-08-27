<script setup lang="ts">
import { computed, watch, ref, onMounted } from 'vue'

const props = defineProps<{
  chunks: string[]
  streaming?: boolean
  speedMs?: number
}>()

const scrollContainer = ref<HTMLElement | null>(null)
const displayText = ref('')
let revealTimer: ReturnType<typeof setTimeout> | null = null
let revealedIdx = 0

const fullText = computed(() => props.chunks.join(''))

const isRevealing = computed(() => displayText.value.length < fullText.value.length)

function startAnimating() {
  const target = fullText.value
  if (revealedIdx >= target.length) {
    if (revealTimer) {
      clearTimeout(revealTimer)
      revealTimer = null
    }
    return
  }

  if (revealTimer) {
    return
  }

  const speed = props.speedMs ?? 12
  const tick = () => {
    const curTarget = fullText.value
    if (revealedIdx >= curTarget.length) {
      revealTimer = null
      return
    }
    revealedIdx += 1
    displayText.value = curTarget.slice(0, revealedIdx)
    scrollToBottom()
    revealTimer = setTimeout(tick, speed)
  }

  tick()
}

function finishAll() {
  if (revealTimer) {
    clearTimeout(revealTimer)
    revealTimer = null
  }
  displayText.value = fullText.value
  revealedIdx = fullText.value.length
}

function scrollToBottom() {
  if (scrollContainer.value) {
    scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  }
}

watch(
  () => props.chunks.length,
  () => {
    startAnimating()
  }
)

watch(
  () => props.streaming,
  (isStreaming) => {
    if (isStreaming) {
      startAnimating()
    } else if (isRevealing.value) {
      startAnimating()
    }
  }
)

onMounted(() => {
  if (fullText.value) {
    if (props.streaming || isRevealing.value) {
      startAnimating()
    } else {
      finishAll()
    }
  }
})
</script>

<template>
  <div ref="scrollContainer" class="stream-wrapper">
    <div class="stream-content">
      <span class="stream-text">{{ displayText }}</span>
      <span v-if="isRevealing" class="stream-cursor" />
    </div>
  </div>
</template>

<style scoped>
.stream-wrapper {
  width: 100%;
  overflow-y: auto;
  max-height: 400px;
}

.stream-content {
  display: inline;
  font-size: 14px;
  line-height: 1.7;
  color: var(--color-text-dark);
  white-space: pre-wrap;
  word-break: break-word;
}

.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--color-primary);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: stream-blink 0.8s step-end infinite;
}

@keyframes stream-blink {
  50% {
    opacity: 0;
  }
}
</style>
