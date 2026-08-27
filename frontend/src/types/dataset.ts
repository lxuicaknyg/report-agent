export type SourceType = 'excel' | 'csv' | 'sql'

export interface User {
  id: string
  username?: string | null
  group_memberships?: string[]
  metadata?: Record<string, unknown>
}

export interface ColumnSchema {
  name: string
  data_type: string
  nullable?: boolean
  description?: string | null
}

export interface SheetInfo {
  sheet_name: string
  columns?: ColumnSchema[]
  row_count?: number | null
}

export interface DataReadRequest {
  sheet_name?: string | null
  columns?: string[] | null
  filters?: Record<string, unknown>
  offset?: number
  limit?: number
}

export interface DataReadResult {
  dataset_id: string
  sheet_name: string
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  offset: number
  limit: number
  has_more?: boolean
}

export interface DatasetInfo {
  dataset_id: string
  name: string
  source_type: SourceType
  source_name?: string | null
  description?: string | null
  row_count?: number | null
  columns?: ColumnSchema[]
  metadata?: Record<string, unknown>
}

export interface DatasetProfile {
  dataset: DatasetInfo
  missing_values?: Record<string, number>
  distinct_values?: Record<string, number>
  sample_rows?: Record<string, unknown>[]
  warnings?: string[]
}

export interface SqlRegisterRequest {
  connection_url: string
  dataset_id: string
  table_name: string
  description?: string
}
