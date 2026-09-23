/**
 * 调你自己后端的接口。
 *
 * 用宿主的 `apiClient`，不要自己写 fetch —— apiClient 会自动带上登录 token，
 * 裸 fetch 发出去没有身份，你的后端会 401。
 *
 * 注意用的是 `apiClient` 而不是 `hostApi`：`hostApi` 是宿主自己的封装，会补
 * `/report/v1` 前缀，用了请求会打到报告后端去。你要写自己的完整命名空间。
 */
import { apiClient } from '../../../services/api/client'
import type { ApiResult } from '../../../types'
import type { ExampleItem, ExampleItemList } from '../types'

/**
 * 你的命名空间，要和模块的 `key` 一致。
 *
 * 实际请求是 /api/example/v1/*，nginx 按 `example` 这一段分发到你的容器。
 * 线上要在 deploy/nginx-modules/ 下加一个对应的 .conf，见那个目录的 README。
 */
const NS = '/example/v1'

export const exampleApi = {
  list(): Promise<ApiResult<ExampleItemList>> {
    return apiClient.get<ExampleItemList>(`${NS}/items`)
  },

  get(itemId: string): Promise<ApiResult<ExampleItem>> {
    return apiClient.get<ExampleItem>(`${NS}/items/${itemId}`)
  },

  create(name: string): Promise<ApiResult<ExampleItem>> {
    return apiClient.post<ExampleItem>(`${NS}/items`, { name })
  },

  upload(file: File): Promise<ApiResult<ExampleItem>> {
    return apiClient.upload<ExampleItem>(`${NS}/items/import`, file)
  },
}
