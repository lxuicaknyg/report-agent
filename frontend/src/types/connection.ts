export type ConnectionDriver = 'mysql' | 'gaussdb' | 'openlookeng'
export type ConnectionStatus = 'untested' | 'ok' | 'failed'

/** One extra field a driver needs beyond host/port/database/credentials. */
export interface DriverExtraField {
  key: string
  label: string
  required?: boolean
  placeholder?: string
}

/** Served by the backend so the form is generated from the same definition it validates against. */
export interface DriverSpec {
  driver: ConnectionDriver
  label: string
  default_port: number
  scheme: string
  requires_database: boolean
  driver_package: string
  note?: string
  extra_fields?: DriverExtraField[]
}

/** A saved connection as the API returns it — never carries the password. */
export interface DataConnection {
  connection_id: string
  name: string
  driver: ConnectionDriver
  host: string
  port: number
  database: string
  username: string
  has_password: boolean
  options: Record<string, unknown>
  description?: string | null
  status: ConnectionStatus
  last_tested_at?: string | null
  last_error?: string | null
  created_at?: string
  updated_at?: string
}

export interface ConnectionInput {
  name: string
  driver: ConnectionDriver
  host: string
  port?: number | null
  database?: string
  username?: string
  /** Omit to keep the stored password; empty string clears it. */
  password?: string | null
  options?: Record<string, unknown>
  description?: string | null
}

export interface ConnectionTestResult {
  success: boolean
  message: string
  elapsed_ms: number
  server_version?: string | null
}

/** What a supplied query is meant to produce: one figure, or detail rows.
 *
 * It comes from the question being answered, not from the user: by the time
 * someone is writing SQL, the system already knows whether the chapter needs a
 * number or a list. It cannot be inferred from the result either — a one-row
 * detail table and a scalar are the same result set. */
export type SupplementShape = 'value' | 'table'

/** What one row of a query result means as a metric value.

 * The convention is positional: the last column carries the number, every
 * column before it names a dimension it was measured on. `error` is set, and
 * `value` left null, when the result cannot be used — several rows, no rows,
 * or a NULL. */
export interface MetricExtraction {
  shape: SupplementShape
  value?: string | null
  dimensions: Record<string, string>
  /** Detail rows, for `shape: 'table'`. Cells arrive as text so the digits
   * shown are the digits the database returned. */
  columns: string[]
  rows: Record<string, string>[]
  truncated: boolean
  error?: string | null
}

/** The outcome of trial-running one statement against a connection.
 *
 * A statement the database refuses comes back with `success: false` rather
 * than as a failed request: the reason belongs beside the editor. */
export interface ConnectionQueryResult {
  success: boolean
  message: string
  connection_name: string
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  truncated: boolean
  elapsed_ms: number
  extraction?: MetricExtraction | null
}

/** A derived analysis that can be generated from a query that already runs. */
export type AnalysisType = 'yoy' | 'mom' | 'ranking'

/** A generated query, offered for review. Never executed by the generator —
 * the user reads it and runs it through the trial run themselves. */
export interface AnalysisSqlResult {
  success: boolean
  message: string
  analysis_type?: AnalysisType | null
  dialect: string
  generated_sql?: string | null
}

/** Text a user pasted, read as a table.
 *
 * Produced by the server, never in the browser: the rows shown in the preview
 * are the rows the supplement carries, and one parser is what makes that true.
 */
export interface ParsedTable {
  columns: string[]
  rows: Record<string, string>[]
  row_count: number
  /** True when the paste held more rows than a supplement may carry. */
  truncated: boolean
  /** How the text was read — "制表符分隔", "指标：数值" — shown because that is
   * a claim about what the user pasted, and they can see it is wrong. */
  format: string
  warnings: string[]
}
