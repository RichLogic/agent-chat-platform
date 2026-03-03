export type SSEEventType = 'run.start' | 'text.delta' | 'run.finish' | 'conversation.title' | 'tool.call' | 'tool.result' | 'messages.sent' | 'provider.fallback' | 'error'

export interface RunStartData {
  run_id: string
  provider: string
  model: string
}

export interface TextDeltaData {
  content: string
}

export interface RunFinishData {
  finish_reason: string
  token_usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
}

export interface ConversationTitleData {
  title: string
}

export interface ToolCallData {
  name: string
  arguments: Record<string, unknown>
  step_index?: number
}

export interface ToolResultData {
  name: string
  result: Record<string, unknown>
  step_index?: number
}

export interface ProviderFallbackData {
  from_provider: string
  to_provider: string
  step_index: number
}

export interface MessagesSentData {
  call_index: number
  messages: Array<{ role: string; content: string }>
}

export interface ErrorData {
  message: string
}

export interface SSEEvent {
  type: SSEEventType
  ts: string
  data: RunStartData | TextDeltaData | RunFinishData | ConversationTitleData | ToolCallData | ToolResultData | MessagesSentData | ProviderFallbackData | ErrorData
}
