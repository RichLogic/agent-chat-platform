import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchSharedConversation, fetchSharedEvents } from '../lib/api'
import type { Message, SharedEvent } from '../types/api'
import { useReplay } from '../hooks/useReplay'
import MessageBubble from '../components/chat/MessageBubble'

const SPEEDS = [1, 2, 5]

export default function ShareReplayPage() {
  const { token } = useParams<{ token: string }>()
  const [title, setTitle] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [events, setEvents] = useState<SharedEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load data
  useEffect(() => {
    if (!token) return
    let cancelled = false

    async function load() {
      try {
        const [convData, eventsData] = await Promise.all([
          fetchSharedConversation(token!),
          fetchSharedEvents(token!),
        ])
        if (cancelled) return
        setTitle(convData.conversation.title)
        setMessages(convData.messages)
        setEvents(eventsData.events)
      } catch (err) {
        if (!cancelled) {
          const status = (err as Error).message
          if (status === '404') {
            setError('分享链接已失效')
          } else {
            setError('加载失败，请稍后重试')
          }
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [token])

  const replay = useReplay(messages, events)

  // Auto-scroll to bottom when new messages appear
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [replay.displayMessages])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface">
        <div className="text-center">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-sm text-text-muted">加载中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-dim">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-text">{error}</h2>
        </div>
      </div>
    )
  }

  const isPlaying = replay.status === 'playing'
  const isFinished = replay.status === 'finished'

  return (
    <div className="flex h-screen flex-col bg-surface">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-dark text-white">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 8V4H8" />
              <rect x="2" y="8" width="20" height="8" rx="2" />
              <path d="M6 20v-4" />
              <path d="M18 20v-4" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-text">{title || 'Shared Conversation'}</h1>
            <p className="text-xs text-text-muted">Shared replay</p>
          </div>
        </div>
        {/* Speed controls */}
        <div className="flex items-center gap-1">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => replay.setSpeed(s)}
              className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                replay.speed === s
                  ? 'bg-primary text-white'
                  : 'bg-surface-dim text-text-muted hover:bg-border'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-6">
          {replay.displayMessages.map((msg, i) => (
            <MessageBubble
              key={msg.id || i}
              message={msg}
              isStreaming={
                replay.status === 'playing' &&
                msg.role === 'assistant' &&
                i === replay.displayMessages.length - 1 &&
                !isFinished
              }
              expandedMode
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Bottom control bar */}
      <div className="border-t border-border bg-white px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center gap-4">
          {/* Play/Pause button */}
          <button
            onClick={() => {
              if (isPlaying) {
                replay.pause()
              } else {
                replay.play()
              }
            }}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-white transition-colors hover:bg-primary/90"
          >
            {isPlaying ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="6,4 20,12 6,20" />
              </svg>
            )}
          </button>

          {/* Progress bar */}
          <div className="flex-1">
            <div className="h-1.5 rounded-full bg-surface-dim">
              <div
                className="h-1.5 rounded-full bg-primary transition-all duration-200"
                style={{ width: `${Math.min(replay.progress * 100, 100)}%` }}
              />
            </div>
          </div>

          {/* Message count */}
          <span className="shrink-0 text-xs text-text-muted">
            {Math.min(replay.displayMessages.length, replay.totalMessages)} / {replay.totalMessages} messages
          </span>

          {/* Restart button */}
          {isFinished && (
            <button
              onClick={replay.restart}
              className="text-xs text-primary transition-colors hover:text-primary/80"
            >
              Restart
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
