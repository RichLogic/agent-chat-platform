import type { Message } from '../../types/api'
import FileAttachment from './FileAttachment'
import Markdown from './Markdown'
import StreamingText from './StreamingText'
import ToolCallStatus from './ToolCallStatus'

interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean
  onViewTrace?: (runId: string) => void
}

export default function MessageBubble({ message, isStreaming, onViewTrace }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const hasToolCalls = message.toolCalls && message.toolCalls.length > 0
  const showMarkdown = !isUser && !isStreaming && message.content

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
          isUser
            ? 'bg-primary text-white'
            : 'bg-surface-dark text-white'
        }`}
      >
        {isUser ? (
          'U'
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 8V4H8" />
            <rect x="2" y="8" width="20" height="8" rx="2" />
            <path d="M6 20v-4" />
            <path d="M18 20v-4" />
          </svg>
        )}
      </div>

      {/* Content */}
      <div className={`max-w-[75%] ${isUser ? 'text-right' : ''}`}>
        {/* File attachments */}
        {message.files && message.files.length > 0 && (
          <FileAttachment files={message.files} />
        )}

        {/* Tool calls (shown before the text response) */}
        {hasToolCalls && (
          <div className="mb-2">
            <ToolCallStatus toolCalls={message.toolCalls!} />
          </div>
        )}

        <div
          className={`inline-block rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-br-md bg-primary text-white'
              : 'rounded-bl-md bg-white text-text shadow-sm ring-1 ring-border'
          }`}
        >
          {isUser ? (
            <span className="whitespace-pre-wrap">{message.content}</span>
          ) : showMarkdown ? (
            <Markdown content={message.content} />
          ) : (
            <StreamingText content={message.content} isStreaming={isStreaming ?? false} />
          )}
        </div>

        {/* Trace button */}
        {!isUser && message.run_id && !isStreaming && (
          <button
            onClick={() => onViewTrace?.(message.run_id!)}
            className="mt-1 text-xs text-text-muted transition-colors hover:text-primary"
          >
            View trace
          </button>
        )}
      </div>
    </div>
  )
}
