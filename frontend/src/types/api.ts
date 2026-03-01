export interface User {
  id: string
  github_login: string
  display_name: string
  avatar_url: string
  email: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationListResponse {
  items: Conversation[]
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result?: Record<string, unknown>
  status: 'calling' | 'done'
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  provider?: string
  model?: string
  run_id?: string
  token_usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  toolCalls?: ToolCall[]
  created_at: string
}

export interface MessageListResponse {
  items: Message[]
}

export interface ChatRequest {
  conversation_id: string
  content: string
}
