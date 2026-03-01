interface StreamingTextProps {
  content: string
  isStreaming: boolean
}

export default function StreamingText({ content, isStreaming }: StreamingTextProps) {
  if (isStreaming && !content) {
    return (
      <span className="inline-flex items-center gap-1 text-text-muted">
        <span className="thinking-dot" />
        <span className="thinking-dot [animation-delay:0.2s]" />
        <span className="thinking-dot [animation-delay:0.4s]" />
        <span className="ml-1.5 text-xs">Thinking</span>
      </span>
    )
  }

  return (
    <span>
      {content}
      {isStreaming && (
        <span className="ml-0.5 inline-block animate-pulse text-text-muted">|</span>
      )}
    </span>
  )
}
