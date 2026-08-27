import type { TaskEvent, SSEConnectionState } from '../../types/events'

type EventHandler = (event: TaskEvent) => void
type ConnectionHandler = (state: SSEConnectionState) => void

const KNOWN_EVENTS = [
  'task.created',
  'plan.generated',
  'plan.updated',
  'tool.started',
  'tool.completed',
  'tool.failed',
  'tool.progress',
  'result.available',
  'task.completed',
  'task.failed',
  'task.cancelled',
  'report.streaming',
  'report.completed',
]

class SSEClient {
  private connection: EventSource | null = null
  private state: SSEConnectionState = {
    status: 'closed',
    last_reconnect_at: null,
    reconnect_attempts: 0,
  }
  private handlers: Map<string, Set<EventHandler | ConnectionHandler>> = new Map()
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private shouldReconnect: boolean = true
  private lastEventId: number = 0

  connect(taskId: string) {
    this.disconnect()
    this.shouldReconnect = true

    this.state.status = 'connecting'
    this.emit('connection', this.state)

    const url = `/api/v1/tasks/${taskId}/events`
    this.connection = new EventSource(url)

    this.connection.onopen = () => {
      this.state.status = 'connected'
      this.state.reconnect_attempts = 0
      this.emit('connection', this.state)
    }

    this.connection.onmessage = (event) => {
      this.handleRawEvent(event.data)
    }

    for (const eventType of KNOWN_EVENTS) {
      this.connection.addEventListener(eventType, (event: MessageEvent) => {
        this.handleRawEvent(event.data)
      })
    }

    this.connection.onerror = () => {
      this.state.status = 'disconnected'
      this.emit('connection', this.state)

      if (this.connection) {
        this.connection.close()
        this.connection = null
      }

      if (this.shouldReconnect) {
        this.scheduleReconnect(taskId)
      }
    }
  }

  private handleRawEvent(rawData: string) {
    try {
      const taskEvent: TaskEvent = JSON.parse(rawData)
      if (taskEvent.id > this.lastEventId) {
        this.lastEventId = taskEvent.id
      }
      this.dispatch(taskEvent)
    } catch {
      console.error('[SSE] Failed to parse event:', rawData)
    }
  }

  private scheduleReconnect(taskId: string) {
    this.state.reconnect_attempts++
    this.state.status = 'reconnecting'
    this.state.last_reconnect_at = new Date().toISOString()
    this.emit('connection', this.state)

    const delay = Math.min(1000 * Math.pow(2, this.state.reconnect_attempts), 30000)

    this.reconnectTimer = setTimeout(() => {
      this.connect(taskId)
    }, delay)
  }

  disconnect() {
    this.shouldReconnect = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.connection) {
      this.connection.close()
      this.connection = null
    }
    this.state.status = 'closed'
    this.emit('connection', this.state)
  }

  on(eventType: string, handler: EventHandler): () => void
  on(eventType: 'connection', handler: ConnectionHandler): () => void
  on(eventType: '*', handler: EventHandler): () => void
  on(eventType: string, handler: EventHandler | ConnectionHandler): () => void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set())
    }
    this.handlers.get(eventType)!.add(handler)

    return () => {
      this.handlers.get(eventType)?.delete(handler)
    }
  }

  private dispatch(event: TaskEvent) {
    const eventType = event.event as string
    this.emit(eventType, event)
    this.emit('*', event)
  }

  private emit(type: string, payload: unknown) {
    this.handlers.get(type)?.forEach((handler) => {
      try {
        (handler as (p: unknown) => void)(payload)
      } catch (error) {
        console.error(`[SSE] Handler error for ${type}:`, error)
      }
    })
  }

  getState(): SSEConnectionState {
    return this.state
  }
}

export const sseClient = new SSEClient()
