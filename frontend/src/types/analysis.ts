import type { DatasetProfile } from './dataset'

export type EvidenceKind = 'dataset' | 'query' | 'research' | 'calculation' | 'generated_sql'

export interface Evidence {
  evidence_id: string
  kind: EvidenceKind
  title: string
  source: string
  value?: unknown
  method?: string | null
  created_at: string
  metadata?: Record<string, unknown>
}

export interface AnalysisRequest {
  question: string
  dataset_id?: string | null
  sql?: string | null
  limit?: number
  metadata?: Record<string, unknown>
}

export interface QueryResult {
  dataset_id: string
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  sql: string
  execution_time_ms?: number | null
}

export interface AnalysisResult {
  question: string
  answer: string
  query_result?: QueryResult | null
  evidence?: Evidence[]
  artifacts?: string[]
}

export type ProfileResult = DatasetProfile
