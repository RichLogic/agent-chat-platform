import { useRef, useState } from 'react'
import { request } from '../lib/api'
import type { FileInfo, Message, MessageListResponse, ToolCall } from '../types/api'
import type { SSEEvent, ToolCallData, ToolResultData } from '../types/events'

export function useStreamChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentRunId, setCurrentRunId] = useState<string | null>(null)
  const onTitleUpdate = useRef<((title: string) => void) | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  async function loadMessages(conversationId: string) {
    const data = await request<MessageListResponse>(
      `/conversations/${conversationId}/messages`,
    )
    setMessages(data.items)
  }

  async function sendMessage(
    conversationId: string,
    content: string,
    fileIds?: string[],
    files?: FileInfo[],
    agentMode?: boolean,
  ) {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      file_ids: fileIds,
      files,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setIsStreaming(true)

    const assistantId = crypto.randomUUID()
    setMessages(prev => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', created_at: new Date().toISOString() },
    ])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          content,
          file_ids: fileIds,
          agent_mode: agentMode ?? false,
        }),
        credentials: 'include',
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.status}`)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''
      let buffer = ''
      let runId: string | null = null
      let toolCalls: ToolCall[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          let event: SSEEvent
          try {
            event = JSON.parse(line.slice(6)) as SSEEvent
          } catch {
            continue
          }

          if (event.type === 'run.start') {
            const data = event.data as { run_id: string }
            runId = data.run_id
            setCurrentRunId(runId)
          } else if (event.type === 'tool.call') {
            const data = event.data as ToolCallData
            toolCalls = [...toolCalls, { name: data.name, arguments: data.arguments, status: 'calling', step_index: data.step_index }]
            const snapshot = [...toolCalls]
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, toolCalls: snapshot } : m,
              ),
            )
          } else if (event.type === 'tool.result') {
            const data = event.data as ToolResultData
            toolCalls = toolCalls.map(tc =>
              tc.name === data.name && tc.status === 'calling' && tc.step_index === data.step_index
                ? { ...tc, result: data.result, status: 'done' as const }
                : tc,
            )
            const snapshot = [...toolCalls]
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, toolCalls: snapshot } : m,
              ),
            )
          } else if (event.type === 'text.delta') {
            const data = event.data as { content: string }
            assistantContent += data.content
            const contentSnapshot = assistantContent
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, content: contentSnapshot } : m,
              ),
            )
          } else if (event.type === 'run.finish') {
            const data = event.data as {
              finish_reason: string
              token_usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
            }
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, run_id: runId ?? undefined, token_usage: data.token_usage }
                  : m,
              ),
            )
          } else if (event.type === 'conversation.title') {
            const data = event.data as { title: string }
            onTitleUpdate.current?.(data.title)
          } else if (event.type === 'error') {
            const data = event.data as { message: string }
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: `Error: ${data.message}` }
                  : m,
              ),
            )
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        console.error('Stream error', err)
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, content: m.content || 'An error occurred.' }
              : m,
          ),
        )
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }

  function stopStreaming() {
    abortRef.current?.abort()
  }

  return {
    messages,
    isStreaming,
    sendMessage,
    loadMessages,
    setMessages,
    currentRunId,
    onTitleUpdate,
    stopStreaming,
  }
}
