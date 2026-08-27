export interface ConversationSession {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Turn {
  id: string
  conversation_id: string
  content: string
  task_id: string
  created_at: string
}
