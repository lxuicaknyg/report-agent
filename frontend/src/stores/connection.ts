import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { connectionApi } from '../services/api/connections'
import type {
  ConnectionInput,
  ConnectionTestResult,
  DataConnection,
  DriverSpec,
} from '../types'

export const useConnectionStore = defineStore('connection', () => {
  const connections = ref<DataConnection[]>([])
  const drivers = ref<DriverSpec[]>([])
  const isLoading = ref(false)
  const isSaving = ref(false)
  /** Which connection is currently being probed — the row shows its own spinner. */
  const testingId = ref<string | null>(null)
  const testResults = ref<Record<string, ConnectionTestResult>>({})
  const error = ref<string | null>(null)

  const driverMap = computed(
    () => new Map(drivers.value.map((item) => [item.driver, item])),
  )

  async function loadDrivers() {
    if (drivers.value.length) return
    const result = await connectionApi.listDrivers()
    if (result.success && result.data) drivers.value = result.data
    else if (result.error) error.value = result.error.message
  }

  async function load() {
    isLoading.value = true
    error.value = null
    try {
      const result = await connectionApi.list()
      if (result.success && Array.isArray(result.data)) connections.value = result.data
      else if (result.error) error.value = result.error.message
    } finally {
      isLoading.value = false
    }
  }

  async function create(input: ConnectionInput): Promise<boolean> {
    isSaving.value = true
    error.value = null
    try {
      const result = await connectionApi.create(input)
      if (!result.success || !result.data) {
        error.value = result.error?.message || '保存失败'
        return false
      }
      connections.value = [result.data, ...connections.value]
      return true
    } finally {
      isSaving.value = false
    }
  }

  async function update(connectionId: string, input: ConnectionInput): Promise<boolean> {
    isSaving.value = true
    error.value = null
    try {
      const result = await connectionApi.update(connectionId, input)
      if (!result.success || !result.data) {
        error.value = result.error?.message || '保存失败'
        return false
      }
      const saved = result.data
      connections.value = connections.value.map((item) =>
        item.connection_id === connectionId ? saved : item,
      )
      // The verdict belonged to the old address or credentials.
      delete testResults.value[connectionId]
      return true
    } finally {
      isSaving.value = false
    }
  }

  async function remove(connectionId: string): Promise<boolean> {
    const result = await connectionApi.remove(connectionId)
    if (!result.success) {
      error.value = result.error?.message || '删除失败'
      return false
    }
    connections.value = connections.value.filter((item) => item.connection_id !== connectionId)
    return true
  }

  async function test(connectionId: string): Promise<ConnectionTestResult | null> {
    testingId.value = connectionId
    error.value = null
    try {
      const result = await connectionApi.test(connectionId)
      if (!result.success || !result.data) {
        error.value = result.error?.message || '测试失败'
        return null
      }
      testResults.value = { ...testResults.value, [connectionId]: result.data }
      // The probe also records its verdict on the connection itself.
      await load()
      return result.data
    } finally {
      testingId.value = null
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    connections,
    drivers,
    driverMap,
    isLoading,
    isSaving,
    testingId,
    testResults,
    error,
    loadDrivers,
    load,
    create,
    update,
    remove,
    test,
    clearError,
  }
})
