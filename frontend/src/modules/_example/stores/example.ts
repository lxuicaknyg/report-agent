import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { exampleApi } from '../services/api'
import type { ExampleItem } from '../types'

/**
 * localStorage 的 key 也要加前缀。宿主用的是 `report-agent:`。
 * 带个版本号，将来改了存储结构可以直接换 key，不用写迁移代码去兼容旧值。
 */
const LS_KEY = 'example:last-query-v1'

/**
 * store id 必须带模块前缀。
 *
 * 宿主已占用：auth / conversation / connection / dataset / report。
 * **撞名不会报错，是静默共用同一份 state** —— 两个模块互相改对方的数据，
 * 排查起来非常痛苦。所以统一用 `<key>-xxx` 的形式。
 */
export const useExampleStore = defineStore('example-main', () => {
  const items = ref<ExampleItem[]>([])
  const loading = ref(false)
  /** 展示给用户的错误文案。接口失败不抛异常，而是落到这里由界面渲染。 */
  const error = ref<string | null>(null)
  const query = ref(loadQuery())

  const visible = computed(() =>
    query.value
      ? items.value.filter((item) => item.name.includes(query.value))
      : items.value,
  )

  function loadQuery(): string {
    if (typeof window === 'undefined') return ''
    return window.localStorage.getItem(LS_KEY) ?? ''
  }

  function setQuery(next: string) {
    query.value = next
    if (typeof window !== 'undefined') window.localStorage.setItem(LS_KEY, next)
  }

  async function refresh() {
    loading.value = true
    error.value = null
    // apiClient 从不抛异常，失败信息在 result.error 里 —— 所以这里不需要
    // try/catch，但**必须**检查 result.success，否则失败会被当成空列表。
    const result = await exampleApi.list()
    loading.value = false
    if (!result.success || !result.data) {
      error.value = result.error?.message ?? '加载失败'
      return
    }
    items.value = result.data.items
  }

  async function create(name: string) {
    const result = await exampleApi.create(name.trim())
    if (!result.success || !result.data) {
      error.value = result.error?.message ?? '创建失败'
      return false
    }
    items.value = [result.data, ...items.value]
    return true
  }

  return { items, visible, loading, error, query, setQuery, refresh, create }
})
