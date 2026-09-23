import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { connectionApi } from '../services/api/connections'
import type {
  AnalysisSqlResult,
  AnalysisType,
  ConnectionInput,
  ConnectionQueryResult,
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

  /**
   * Trial-run a statement so the user can see what it would supply.
   *
   * Rejected SQL is a result, not a failure: it comes back on the payload with
   * `success: false` and is rendered beside the editor. Only a transport-level
   * problem goes through `error`, and it is returned rather than stored — two
   * question cards can be running their own queries at once, and one card's
   * failure must not paint the other.
   */
  async function query(
    connectionId: string,
    sql: string,
    shape: 'value' | 'table' = 'value',
  ): Promise<ConnectionQueryResult> {
    const result = await connectionApi.query(connectionId, sql, shape)
    if (result.success && result.data) return result.data
    return {
      success: false,
      message: result.error?.message || '取数失败',
      connection_name: '',
      columns: [],
      rows: [],
      row_count: 0,
      truncated: false,
      elapsed_ms: 0,
      extraction: null,
    }
  }

  /**
   * Ask for a derived-analysis rewrite of a query.
   *
   * Like `query`, a refusal comes back on the payload rather than through the
   * shared `error`: two cards can be generating at once and one card's failure
   * must not paint the other.
   */
  async function analysisSql(
    connectionId: string,
    sql: string,
    analysisType: AnalysisType,
  ): Promise<AnalysisSqlResult> {
    const result = await connectionApi.analysisSql(connectionId, sql, analysisType)
    if (result.success && result.data) return result.data
    return {
      success: false,
      message: result.error?.message || '生成失败',
      dialect: '',
      generated_sql: null,
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
    query,
    analysisSql,
    clearError,
  }
})
