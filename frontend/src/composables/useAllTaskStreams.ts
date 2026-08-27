import { reactive } from 'vue'

export interface TaskStreamState {
  chunks: string[]
  isStreaming: boolean
}

interface StreamStore {
  [taskId: string]: TaskStreamState
}

const store = reactive<StreamStore>({})

export function useAllTaskStreams() {
  const streamedTasks = reactive<Set<string>>(new Set())

  function getStream(taskId: string): TaskStreamState {
    if (!store[taskId]) {
      store[taskId] = { chunks: [], isStreaming: false }
    }
    return store[taskId]
  }

  function handleSSEStreamingEvent(taskId: string, delta: string) {
    const s = getStream(taskId)
    if (!s.isStreaming) {
      s.chunks = []
      s.isStreaming = true
    }
    if (delta) {
      s.chunks = [...s.chunks, delta]
    }
  }

  function handleSSEStreamingCompleted(taskId: string) {
    if (store[taskId]) {
      store[taskId].isStreaming = false
    }
    streamedTasks.add(taskId)
  }

  function handleSSEStreamingFailed(taskId: string) {
    if (store[taskId]) {
      store[taskId].isStreaming = false
    }
    streamedTasks.add(taskId)
  }

  function cleanup(taskId: string) {
    delete store[taskId]
    streamedTasks.delete(taskId)
  }

  function isStreamed(taskId: string): boolean {
    return streamedTasks.has(taskId)
  }

  return {
    store,
    getStream,
    handleSSEStreamingEvent,
    handleSSEStreamingCompleted,
    handleSSEStreamingFailed,
    cleanup,
    isStreamed,
  }
}
