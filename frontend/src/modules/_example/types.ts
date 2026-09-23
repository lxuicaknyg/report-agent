/** 你的后端返回的数据结构。和宿主的 types/ 分开，互不干扰。 */
export interface ExampleItem {
  item_id: string
  name: string
  /** 后端用 snake_case，前端就照抄，别在类型层做一次改名——两边对不上时更难查。 */
  updated_at: string
  status: 'draft' | 'ready' | 'failed'
}

export interface ExampleItemList {
  total: number
  items: ExampleItem[]
}
