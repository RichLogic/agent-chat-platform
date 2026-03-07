import { useCallback, useRef, useState } from 'react'
import { getActiveRun, pollRunEvents, request } from '../lib/api'
import type {
  ConversationCacheEntry,
  FileInfo,
  Message,
  MessageListResponse,
  ToolCall,
} from '../types/api'
import type { SSEEvent, ToolCallData, ToolResultData } from '../types/events'

export function useStreamChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const onTitleUpdate = useRef<((title: string) => void) | null>(null)

  // Per-conversation state
  const cacheRef = useRef<Map<string, ConversationCacheEntry>>(new Map())
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())
  const pollIntervalsRef = useRef<Map<string, number>>(new Map())
  const activeConvIdRef = useRef<string | null>(null)

  // Track tool calls per assistant message across events
  const toolCallsMapRef = useRef<Map<string, ToolCall[]>>(new Map())
  // Track assistant content per message
  const contentMapRef = useRef<Map<string, string>>(new Map())

  function getCache(convId: string): ConversationCacheEntry {
    let entry = cacheRef.current.get(convId)
    if (!entry) {
      entry = { messages: [], isStreaming: false, runId: null, pollOffset: 0 }
      cacheRef.current.set(convId, entry)
    }
    return entry
  }

  function updateCache(convId: string, update: Partial<ConversationCacheEntry>) {
    const entry = getCache(convId)
    Object.assign(entry, update)
    // Sync to React state if this is the active conversation
    if (convId === activeConvIdRef.current) {
      if (update.messages !== undefined) setMessages([...entry.messages])
      if (update.isStreaming !== undefined) setIsStreaming(entry.isStreaming)
    }
  }

  function processEvent(convId: string, event: SSEEvent, assistantId: string) {
    const cache = getCache(convId)

    if (event.type === 'run.start') {
      const data = event.data as { run_id: string }
      cache.runId = data.run_id
    } else if (event.type === 'tool.call') {
      const data = event.data as ToolCallData
      const existing = toolCallsMapRef.current.get(assistantId) ?? []
      const updated = [
        ...existing,
        { name: data.name, arguments: data.arguments, status: 'calling' as const, step_index: data.step_index },
      ]
      toolCallsMapRef.current.set(assistantId, updated)
      cache.messages = cache.messages.map(m =>
        m.id === assistantId ? { ...m, toolCalls: [...updated] } : m,
      )
    } else if (event.type === 'tool.result') {
      const data = event.data as ToolResultData
      const existing = toolCallsMapRef.current.get(assistantId) ?? []
      const updated = existing.map(tc =>
        tc.name === data.name && tc.status === 'calling' && tc.step_index === data.step_index
          ? { ...tc, result: data.result, status: 'done' as const }
          : tc,
      )
      toolCallsMapRef.current.set(assistantId, updated)
      cache.messages = cache.messages.map(m =>
        m.id === assistantId ? { ...m, toolCalls: [...updated] } : m,
      )
    } else if (event.type === 'text.delta') {
      const data = event.data as { content: string }
      const current = contentMapRef.current.get(assistantId) ?? ''
      const updated = current + data.content
      contentMapRef.current.set(assistantId, updated)
      cache.messages = cache.messages.map(m =>
        m.id === assistantId ? { ...m, content: updated } : m,
      )
    } else if (event.type === 'run.finish') {
      const data = event.data as {
        finish_reason: string
        token_usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
      }
      cache.messages = cache.messages.map(m =>
        m.id === assistantId
          ? { ...m, run_id: cache.runId ?? undefined, token_usage: data.token_usage }
          : m,
      )
      cache.isStreaming = false
    } else if (event.type === 'conversation.title') {
      const data = event.data as { title: string }
      onTitleUpdate.current?.(data.title)
    } else if (event.type === 'error') {
      const data = event.data as { message: string }
      cache.messages = cache.messages.map(m =>
        m.id === assistantId ? { ...m, content: `Error: ${data.message}` } : m,
      )
      cache.isStreaming = false
    }

    // Sync to React if active
    if (convId === activeConvIdRef.current) {
      setMessages([...cache.messages])
      setIsStreaming(cache.isStreaming)
    }
  }

  const sendMessage = useCallback(
    async (
      conversationId: string,
      content: string,
      fileIds?: string[],
      files?: FileInfo[],
      agentMode?: boolean,
    ) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        file_ids: fileIds,
        files,
        created_at: new Date().toISOString(),
      }

      const assistantId = crypto.randomUUID()
      const assistantMsg: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
      }

      const cache = getCache(conversationId)
      cache.messages = [...cache.messages, userMsg, assistantMsg]
      cache.isStreaming = true
      cache.runId = null

      // Reset tracking for this assistant message
      toolCallsMapRef.current.set(assistantId, [])
      contentMapRef.current.set(assistantId, '')

      updateCache(conversationId, { messages: cache.messages, isStreaming: true })

      const controller = new AbortController()
      abortControllersRef.current.set(conversationId, controller)

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
        let buffer = ''

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

            processEvent(conversationId, event, assistantId)
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          console.error('Stream error', err)
          const cache = getCache(conversationId)
          cache.messages = cache.messages.map(m =>
            m.id === assistantId
              ? { ...m, content: m.content || 'An error occurred.' }
              : m,
          )
        }
      } finally {
        const cache = getCache(conversationId)
        cache.isStreaming = false
        abortControllersRef.current.delete(conversationId)
        // Clean up tracking maps
        toolCallsMapRef.current.delete(assistantId)
        contentMapRef.current.delete(assistantId)
        if (conversationId === activeConvIdRef.current) {
          setMessages([...cache.messages])
          setIsStreaming(false)
        }
      }
    },
    [],
  )

  function startPolling(convId: string, runId: string, offset: number, assistantId: string) {
    // Clear any existing poll for this conversation
    const existing = pollIntervalsRef.current.get(convId)
    if (existing) clearInterval(existing)

    // Initialize tracking for this assistant message
    toolCallsMapRef.current.set(assistantId, [])
    contentMapRef.current.set(assistantId, '')

    const pollStartTime = Date.now()
    const MAX_POLL_DURATION = 5 * 60 * 1000 // 5 minutes max

    const intervalId = window.setInterval(async () => {
      try {
        // Safety: stop polling if it's been running too long (zombie run protection)
        if (Date.now() - pollStartTime > MAX_POLL_DURATION) {
          console.warn('Polling timeout — possible zombie run', runId)
          clearInterval(intervalId)
          pollIntervalsRef.current.delete(convId)
          const cache = getCache(convId)
          cache.isStreaming = false
          if (convId === activeConvIdRef.current) {
            setIsStreaming(false)
          }
          return
        }

        const cache = getCache(convId)
        const result = await pollRunEvents(runId, cache.pollOffset)

        for (const event of result.events) {
          processEvent(convId, event as unknown as SSEEvent, assistantId)
        }
        cache.pollOffset = result.next_offset

        if (result.run_status !== 'running') {
          // Stop polling
          clearInterval(intervalId)
          pollIntervalsRef.current.delete(convId)
          toolCallsMapRef.current.delete(assistantId)
          contentMapRef.current.delete(assistantId)

          // Reload final messages from DB for consistency
          const data = await request<MessageListResponse>(
            `/conversations/${convId}/messages`,
          )
          cache.messages = data.items
          cache.isStreaming = false
          if (convId === activeConvIdRef.current) {
            setMessages([...cache.messages])
            setIsStreaming(false)
          }
        }
      } catch (err) {
        console.error('Poll error', err)
        clearInterval(intervalId)
        pollIntervalsRef.current.delete(convId)
        const cache = getCache(convId)
        cache.isStreaming = false
        if (convId === activeConvIdRef.current) {
          setIsStreaming(false)
        }
      }
    }, 1000)

    pollIntervalsRef.current.set(convId, intervalId)
  }

  const switchConversation = useCallback(async (convId: string) => {
    activeConvIdRef.current = convId
    const cache = cacheRef.current.get(convId)

    if (cache) {
      // Restore from cache immediately
      setMessages([...cache.messages])
      setIsStreaming(cache.isStreaming)
      return
    }

    // No cache — load messages from API
    const data = await request<MessageListResponse>(
      `/conversations/${convId}/messages`,
    )
    const entry = getCache(convId)
    entry.messages = data.items

    // Check for active run
    try {
      const { active_run } = await getActiveRun(convId)
      if (active_run) {
        // There's a running run — create placeholder and start polling
        const assistantId = crypto.randomUUID()
        const placeholder: Message = {
          id: assistantId,
          role: 'assistant',
          content: '',
          created_at: new Date().toISOString(),
        }
        entry.messages = [...entry.messages, placeholder]
        entry.isStreaming = true
        entry.runId = active_run.id
        entry.pollOffset = 0

        if (convId === activeConvIdRef.current) {
          setMessages([...entry.messages])
          setIsStreaming(true)
        }

        startPolling(convId, active_run.id, 0, assistantId)
        return
      }
    } catch {
      // Active run check failed, just show messages
    }

    entry.isStreaming = false
    if (convId === activeConvIdRef.current) {
      setMessages([...entry.messages])
      setIsStreaming(false)
    }
  }, [])

  const clearConversation = useCallback((convId: string) => {
    // Stop any active SSE or polling
    const controller = abortControllersRef.current.get(convId)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(convId)
    }
    const pollId = pollIntervalsRef.current.get(convId)
    if (pollId) {
      clearInterval(pollId)
      pollIntervalsRef.current.delete(convId)
    }

    activeConvIdRef.current = convId
    cacheRef.current.set(convId, {
      messages: [],
      isStreaming: false,
      runId: null,
      pollOffset: 0,
    })
    setMessages([])
    setIsStreaming(false)
  }, [])

  function stopStreaming() {
    const convId = activeConvIdRef.current
    if (!convId) return

    // Abort SSE
    const controller = abortControllersRef.current.get(convId)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(convId)
    }

    // Stop polling
    const pollId = pollIntervalsRef.current.get(convId)
    if (pollId) {
      clearInterval(pollId)
      pollIntervalsRef.current.delete(convId)
    }

    const cache = getCache(convId)
    cache.isStreaming = false
    setIsStreaming(false)
  }

  return {
    messages,
    isStreaming,
    sendMessage,
    switchConversation,
    clearConversation,
    onTitleUpdate,
    stopStreaming,
  }
}
