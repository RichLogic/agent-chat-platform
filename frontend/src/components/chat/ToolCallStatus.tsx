import { useState } from 'react'
import type { ToolCall } from '../../types/api'

interface ToolCallStatusProps {
  toolCalls: ToolCall[]
  defaultExpanded?: boolean
}

const TOOL_LABELS: Record<string, string> = {
  weather: 'Weather',
  news: 'News',
  search: 'Search',
  read_pdf: 'Read PDF',
  search_memory: 'Memory',
  kb_search: 'KB Search',
}

function ToolCallItem({ toolCall, defaultExpanded = false }: { toolCall: ToolCall; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const isCalling = toolCall.status === 'calling'
  const label = TOOL_LABELS[toolCall.name] || toolCall.name
  const args = toolCall.arguments as Record<string, string>

  function getCallingText() {
    if (toolCall.name === 'weather') {
      return `Querying ${args.city ? args.city + ' ' : ''}weather...`
    }
    if (toolCall.name === 'news') {
      const parts = [args.country, args.category].filter(Boolean).join(' ')
      return `Fetching ${parts ? parts + ' ' : ''}news...`
    }
    if (toolCall.name === 'search') {
      return `Searching: ${args.query || ''}...`
    }
    if (toolCall.name === 'read_pdf') {
      return `Reading PDF${args.file_id ? ' ...' + String(args.file_id).slice(-6) : ''}...`
    }
    if (toolCall.name === 'search_memory') {
      return `Searching memory: ${args.query || ''}...`
    }
    if (toolCall.name === 'kb_search') {
      return `Searching knowledge base: ${args.query || ''}...`
    }
    return `Calling ${label}...`
  }

  function getDoneText() {
    if (toolCall.name === 'weather') return `${label}: ${args.city || ''}`
    if (toolCall.name === 'news') {
      const parts = [args.country, args.category].filter(Boolean).join(' / ')
      return `${label}: ${parts || 'headlines'}`
    }
    if (toolCall.name === 'search') {
      return `${label}: ${args.query || ''}`
    }
    if (toolCall.name === 'read_pdf') {
      return `${label}: ${args.file_id ? '...' + String(args.file_id).slice(-6) : 'document'}`
    }
    if (toolCall.name === 'search_memory') {
      return `${label}: ${args.query || ''}`
    }
    if (toolCall.name === 'kb_search') {
      return `${label}: ${args.query || ''}`
    }
    return label
  }

  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs">
      <div
        className="flex cursor-pointer items-center gap-2"
        onClick={() => !isCalling && setExpanded(!expanded)}
      >
        {isCalling ? (
          <svg className="h-3.5 w-3.5 animate-spin text-primary" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <svg className="h-3.5 w-3.5 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}
        <span className="font-medium text-text">
          {isCalling ? getCallingText() : getDoneText()}
        </span>
        {!isCalling && (
          <svg
            className={`ml-auto h-3 w-3 text-text-muted transition-transform ${expanded ? 'rotate-180' : ''}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        )}
      </div>

      {expanded && toolCall.result && (
        <div className="mt-2 border-t border-border pt-2">
          {toolCall.name === 'weather' && <WeatherResult result={toolCall.result} />}
          {toolCall.name === 'news' && <NewsResult result={toolCall.result} />}
          {toolCall.name === 'search' && <SearchResult result={toolCall.result} />}
          {toolCall.name === 'kb_search' && <KBSearchResult result={toolCall.result} />}
          {!['weather', 'news', 'search', 'kb_search'].includes(toolCall.name) && (
            <pre className="whitespace-pre-wrap text-text-muted">{JSON.stringify(toolCall.result, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  )
}

function WeatherResult({ result }: { result: Record<string, unknown> }) {
  if (result.error) {
    return <span className="text-red-600">{String(result.error)}</span>
  }

  const units = (result.units || {}) as Record<string, string>

  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-text-muted">
      <span>Location</span>
      <span className="text-text">{String(result.city)}, {String(result.country)}</span>
      <span>Weather</span>
      <span className="text-text">{String(result.weather)}</span>
      <span>Temperature</span>
      <span className="text-text">{String(result.temperature)}{units.temperature}</span>
      <span>Feels like</span>
      <span className="text-text">{String(result.apparent_temperature)}{units.temperature}</span>
      <span>Humidity</span>
      <span className="text-text">{String(result.humidity)}{units.humidity}</span>
      <span>Wind</span>
      <span className="text-text">{String(result.wind_speed)} {units.wind_speed}</span>
    </div>
  )
}

function NewsResult({ result }: { result: Record<string, unknown> }) {
  if (result.error) {
    return <span className="text-red-600">{String(result.error)}</span>
  }

  const articles = (result.articles || []) as Array<{
    title: string
    source: string
    description: string
    url: string
    published_at: string
  }>

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-text-muted">
        {String(result.country).toUpperCase()} / {String(result.category)} — {String(result.total_results)} results
      </span>
      {articles.map((a, i) => (
        <div key={i} className="border-t border-border pt-1">
          <a
            href={a.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-primary hover:underline"
          >
            {a.title}
          </a>
          <div className="text-text-muted">
            {a.source}{a.published_at ? ` · ${new Date(a.published_at).toLocaleString()}` : ''}
          </div>
          {a.description && <p className="text-text">{a.description}</p>}
        </div>
      ))}
    </div>
  )
}

function SearchResult({ result }: { result: Record<string, unknown> }) {
  if (result.error) {
    return <span className="text-red-600">{String(result.error)}</span>
  }

  const results = (result.results || []) as Array<{
    title: string
    snippet: string
    url: string
    source: string
  }>

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-text-muted">
        {String(result.engine)} — {results.length} results
      </span>
      {results.map((r, i) => (
        <div key={i} className="border-t border-border pt-1">
          <a
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-primary hover:underline"
          >
            {r.title}
          </a>
          {r.source && <div className="text-text-muted">{r.source}</div>}
          {r.snippet && <p className="text-text">{r.snippet}</p>}
        </div>
      ))}
    </div>
  )
}

function KBSearchResult({ result }: { result: Record<string, unknown> }) {
  if (result.error) {
    return <span className="text-red-600">{String(result.error)}</span>
  }

  const results = (result.results || []) as Array<{
    source_title: string
    source_type: string
    content: string
    relevance: number
    page_number?: number
    url?: string
  }>

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-text-muted">
        {results.length} results for &quot;{String(result.query)}&quot;
      </span>
      {results.map((r, i) => (
        <div key={i} className="border-t border-border pt-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-text">{r.source_title}</span>
            <span className="text-text-muted text-[10px]">{r.source_type}</span>
            {r.page_number && <span className="text-text-muted text-[10px]">p.{r.page_number}</span>}
            <span className="ml-auto text-text-muted text-[10px]">{(r.relevance * 100).toFixed(0)}%</span>
          </div>
          <p className="text-text line-clamp-3">{r.content}</p>
        </div>
      ))}
    </div>
  )
}

export default function ToolCallStatus({ toolCalls, defaultExpanded }: ToolCallStatusProps) {
  return (
    <div className="flex flex-col gap-2">
      {toolCalls.map((tc, i) => (
        <ToolCallItem key={`${tc.name}-${i}`} toolCall={tc} defaultExpanded={defaultExpanded} />
      ))}
    </div>
  )
}
