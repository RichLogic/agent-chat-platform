import { useEffect, useRef } from 'react'
import type { Message } from '../../types/api'
import MessageBubble from './MessageBubble'

interface ChatAreaProps {
  messages: Message[]
  isStreaming: boolean
  onViewTrace?: (runId: string) => void
}

export default function ChatArea({ messages, isStreaming, onViewTrace }: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface-dim">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-text-muted">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-text">Start a conversation</h2>
          <p className="mt-1 text-sm text-text-muted">Send a message to begin chatting.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-6">
        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isStreaming={isStreaming && msg.role === 'assistant' && i === messages.length - 1}
            onViewTrace={onViewTrace}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
