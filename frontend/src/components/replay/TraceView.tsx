import { useEffect, useState } from 'react'
import type { SSEEvent } from '../../types/events'

interface TraceViewProps {
  runId: string
  onClose: () => void
  defaultExpandAll?: boolean
}

type TraceEntryType = 'run.start' | 'messages.sent' | 'text' | 'tool.call' | 'tool.result' | 'provider.fallback' | 'llm.usage' | 'run.finish' | 'error'

interface TraceEntry {
  type: TraceEntryType
  ts: string
  label: string
  detail: string
  collapsed?: boolean
  stepIndex?: number
}

function CollapsibleEntry({ entry, defaultOpen = false, stepDuration }: { entry: TraceEntry; defaultOpen?: boolean; stepDuration?: string }) {
  const [open, setOpen] = useState(defaultOpen)
  const isLong = entry.detail.length > 120
  const canToggle = isLong || entry.type === 'messages.sent'

  const typeStyles: Record<string, string> = {
    'run.start': 'border-l-success',
    'run.finish': 'border-l-success',
    'messages.sent': 'border-l-blue-400',
    text: 'border-l-primary',
    'tool.call': 'border-l-amber-400',
    'tool.result': 'border-l-amber-400',
    'provider.fallback': 'border-l-yellow-400',
    'llm.usage': 'border-l-emerald-400',
    error: 'border-l-error',
  }

  const typeBadge: Record<string, string> = {
    'run.start': 'bg-success/15 text-success',
    'run.finish': 'bg-success/15 text-success',
    'messages.sent': 'bg-blue-500/15 text-blue-600',
    text: 'bg-primary/15 text-primary',
    'tool.call': 'bg-amber-500/15 text-amber-700',
    'tool.result': 'bg-amber-500/15 text-amber-700',
    'provider.fallback': 'bg-yellow-500/15 text-yellow-700',
    'llm.usage': 'bg-emerald-500/15 text-emerald-700',
    error: 'bg-error/15 text-error',
  }

  return (
    <div className={`mb-1.5 border-l-2 ${typeStyles[entry.type] ?? 'border-l-border'}`}>
      <div
        className={`flex items-center gap-2 py-1 pl-3 ${canToggle ? 'cursor-pointer select-none' : ''}`}
        onClick={() => canToggle && setOpen(v => !v)}
      >
        {canToggle && (
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`shrink-0 text-text-muted transition-transform ${open ? 'rotate-90' : ''}`}
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
        )}
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${typeBadge[entry.type] ?? 'bg-border text-text-muted'}`}>
          {entry.type}
        </span>
        <span className="flex-1 truncate text-xs text-text">{entry.label}</span>
        {stepDuration && (
          <span className="shrink-0 rounded bg-amber-500/10 px-1 text-[10px] text-amber-700">
            {stepDuration}
          </span>
        )}
        {entry.ts && (
          <span className="shrink-0 text-[10px] text-text-muted">
            {new Date(entry.ts).toLocaleTimeString()}
          </span>
        )}
      </div>
      {open && (
        <pre className="mx-3 mb-1 max-h-80 overflow-auto rounded bg-surface-dark p-2 text-[11px] leading-relaxed text-white">
          {entry.detail}
        </pre>
      )}
      {!canToggle && entry.detail && (
        <p className="mt-0.5 pl-3 text-xs text-text whitespace-pre-wrap">{entry.detail}</p>
      )}
    </div>
  )
}

export default function TraceView({ runId, onClose, defaultExpandAll }: TraceViewProps) {
  const [entries, setEntries] = useState<TraceEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()

    async function loadEvents() {
      try {
        const response = await fetch(`/api/runs/${runId}/events`, {
          credentials: 'include',
          signal: controller.signal,
        })

        if (!response.ok) {
          setEntries([{ type: 'error', ts: '', label: `Failed to load (${response.status})`, detail: '' }])
          setLoading(false)
          return
        }

        const reader = response.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let textContent = ''
        let textCallIndex = 0
        const result: TraceEntry[] = []

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
              const d = event.data as { provider: string; model: string }
              result.push({
                type: 'run.start',
                ts: event.ts,
                label: `${d.provider} / ${d.model}`,
                detail: '',
              })
            } else if (event.type === 'messages.sent') {
              const d = event.data as { call_index: number; messages: Array<{ role: string; content: string }> }
              const msgCount = d.messages.length
              const formatted = d.messages
                .map((m, i) => `── [${i + 1}] ${m.role.toUpperCase()} ──\n${m.content}`)
                .join('\n\n')
              result.push({
                type: 'messages.sent',
                ts: event.ts,
                label: `LLM Call #${d.call_index + 1} — ${msgCount} message${msgCount > 1 ? 's' : ''} sent`,
                detail: formatted,
              })
              textCallIndex = d.call_index
            } else if (event.type === 'text.delta') {
              const d = event.data as { content: string }
              textContent += d.content
            } else if (event.type === 'tool.call') {
              // Flush text before tool call
              if (textContent) {
                result.push({
                  type: 'text',
                  ts: '',
                  label: `LLM Call #${textCallIndex + 1} Response (tool call detected)`,
                  detail: textContent,
                })
                textContent = ''
              }
              const d = event.data as { name: string; arguments: Record<string, unknown>; step_index?: number }
              const stepLabel = d.step_index != null ? `Step ${d.step_index}: ` : ''
              result.push({
                type: 'tool.call',
                ts: event.ts,
                label: `${stepLabel}${d.name}(${JSON.stringify(d.arguments)})`,
                detail: JSON.stringify(d.arguments, null, 2),
                stepIndex: d.step_index,
              })
            } else if (event.type === 'tool.result') {
              const d = event.data as { name: string; result: Record<string, unknown>; step_index?: number }
              const resultStr = JSON.stringify(d.result, null, 2)
              const stepLabel = d.step_index != null ? `Step ${d.step_index}: ` : ''
              result.push({
                type: 'tool.result',
                ts: event.ts,
                label: `${stepLabel}${d.name} → result`,
                detail: resultStr,
                stepIndex: d.step_index,
              })
            } else if (event.type === 'provider.fallback') {
              const d = event.data as { from_provider: string; to_provider: string; step_index: number }
              result.push({
                type: 'provider.fallback',
                ts: event.ts,
                label: `Fallback: ${d.from_provider} → ${d.to_provider}`,
                detail: `Provider ${d.from_provider} failed, switching to ${d.to_provider}`,
                stepIndex: d.step_index,
              })
            } else if (event.type === 'llm.usage') {
              const d = event.data as { call_index: number; token_usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number } }
              const u = d.token_usage
              result.push({
                type: 'llm.usage',
                ts: event.ts,
                label: `LLM Call #${d.call_index + 1} — ${u.prompt_tokens} in + ${u.completion_tokens} out = ${u.total_tokens} tokens`,
                detail: '',
              })
            } else if (event.type === 'run.finish') {
              // Flush remaining text
              if (textContent) {
                result.push({
                  type: 'text',
                  ts: '',
                  label: `LLM Call #${textCallIndex + 1} Response`,
                  detail: textContent,
                })
                textContent = ''
              }
              const d = event.data as { finish_reason: string; token_usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } }
              const usage = d.token_usage
                ? `Tokens: ${d.token_usage.prompt_tokens} in + ${d.token_usage.completion_tokens} out = ${d.token_usage.total_tokens}`
                : ''
              result.push({
                type: 'run.finish',
                ts: event.ts,
                label: `${d.finish_reason}${usage ? ' | ' + usage : ''}`,
                detail: '',
              })
            } else if (event.type === 'error') {
              const d = event.data as { message: string }
              result.push({
                type: 'error',
                ts: event.ts,
                label: d.message,
                detail: '',
              })
            }
          }
        }

        // Flush any remaining text
        if (textContent) {
          result.push({
            type: 'text',
            ts: '',
            label: `LLM Call #${textCallIndex + 1} Response`,
            detail: textContent,
          })
        }

        setEntries(result)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setEntries(prev => [...prev, { type: 'error', ts: '', label: 'Failed to load events', detail: '' }])
        }
      } finally {
        setLoading(false)
      }
    }

    loadEvents()
    return () => controller.abort()
  }, [runId])

  return (
    <div className="border-t border-border bg-surface-dim">
      <div className="flex items-center justify-between px-4 py-2">
        <span className="text-xs font-medium text-text-muted">Run Trace — {runId.slice(0, 8)}</span>
        <button
          onClick={onClose}
          className="rounded p-1 text-text-muted transition-colors hover:bg-border hover:text-text"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="max-h-80 overflow-y-auto px-4 pb-3">
        {loading && (
          <p className="py-4 text-center text-xs text-text-muted">Loading events...</p>
        )}
        {!loading && entries.length === 0 && (
          <p className="py-4 text-center text-xs text-text-muted">No events found.</p>
        )}
        {entries.map((entry, i) => {
          // Compute step duration for tool.result entries
          let stepDuration: string | undefined
          if (entry.type === 'tool.result' && entry.ts && entry.stepIndex != null) {
            const matchingCall = entries.find(
              e => e.type === 'tool.call' && e.stepIndex === entry.stepIndex && e.ts,
            )
            if (matchingCall) {
              const ms = new Date(entry.ts).getTime() - new Date(matchingCall.ts).getTime()
              stepDuration = ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
            }
          }
          return (
            <CollapsibleEntry
              key={i}
              entry={entry}
              defaultOpen={defaultExpandAll}
              stepDuration={stepDuration}
            />
          )
        })}
      </div>
    </div>
  )
}
