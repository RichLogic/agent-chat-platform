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
  step_index?: number
}

export interface FileInfo {
  id: string
  original_filename: string
  size_bytes: number
  page_count?: number | null
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
  file_ids?: string[]
  files?: FileInfo[]
  created_at: string
}

export interface MessageListResponse {
  items: Message[]
}

export interface ChatRequest {
  conversation_id: string
  content: string
  file_ids?: string[]
}

export interface UploadFileResponse {
  id: string
  original_filename: string
  size_bytes: number
  page_count?: number | null
  parse_status: string
  is_duplicate: boolean
}

export interface ShareResponse {
  shared: boolean
  share_token?: string
  share_url?: string
}

export interface CreateShareResponse {
  share_token: string
  share_url: string
}

export interface SharedConversation {
  conversation: { title: string; created_at: string }
  messages: Message[]
}

export interface SharedEvent {
  run_id: string
  type: string
  ts: string
  data: Record<string, unknown>
}

export interface SharedEventsResponse {
  events: SharedEvent[]
}

export interface ConversationCacheEntry {
  messages: Message[]
  isStreaming: boolean
  runId: string | null
  pollOffset: number
}

export interface ActiveRunResponse {
  active_run: { id: string; status: string } | null
}

export interface PollRunResponse {
  events: Array<{ type: string; ts: string; data: Record<string, unknown> }>
  next_offset: number
  run_status: 'running' | 'finished' | 'failed'
}
