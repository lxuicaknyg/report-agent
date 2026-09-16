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
