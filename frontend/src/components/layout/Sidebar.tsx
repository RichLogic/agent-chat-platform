import { useEffect, useRef, useState } from 'react'
import type { Conversation } from '../../types/api'

interface SidebarProps {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}

function ConversationItem({
  conv,
  isActive,
  onSelect,
  onDelete,
}: {
  conv: Conversation
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [removing, setRemoving] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null)

  // Auto-cancel confirmation after 3s
  useEffect(() => {
    if (confirming) {
      timerRef.current = setTimeout(() => setConfirming(false), 3000)
      return () => { if (timerRef.current) clearTimeout(timerRef.current) }
    }
  }, [confirming])

  function handleDeleteClick(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirming) {
      setConfirming(true)
      return
    }
    // Confirmed — play remove animation then delete
    if (timerRef.current) clearTimeout(timerRef.current)
    setConfirming(false)
    setRemoving(true)
  }

  function handleCancel(e: React.MouseEvent) {
    e.stopPropagation()
    if (timerRef.current) clearTimeout(timerRef.current)
    setConfirming(false)
  }

  return (
    <div
      className={`group relative mb-0.5 flex cursor-pointer items-center rounded-lg px-3 py-2.5 text-sm transition-all duration-300 ${
        removing
          ? '-translate-x-full opacity-0'
          : isActive
            ? 'bg-white/15 text-white'
            : 'text-white/70 hover:bg-white/10 hover:text-white'
      }`}
      onClick={onSelect}
      onTransitionEnd={() => {
        if (removing) onDelete()
      }}
    >
      <span className="flex-1 truncate">{conv.title || 'New Chat'}</span>

      {confirming ? (
        <div className="ml-1 flex shrink-0 items-center gap-1" onClick={e => e.stopPropagation()}>
          <span className="text-xs text-red-400">Delete?</span>
          <button
            onClick={handleDeleteClick}
            className="rounded p-0.5 text-red-400 transition-colors hover:bg-red-500/20"
            title="Confirm delete"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>
          <button
            onClick={handleCancel}
            className="rounded p-0.5 text-white/50 transition-colors hover:bg-white/10"
            title="Cancel"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      ) : (
        <button
          onClick={handleDeleteClick}
          className="ml-1 shrink-0 rounded p-1 opacity-0 transition-opacity hover:bg-white/10 group-hover:opacity-100"
          title="Delete"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </button>
      )}
    </div>
  )
}

export default function Sidebar({ conversations, activeId, onSelect, onCreate, onDelete }: SidebarProps) {
  return (
    <div className="flex h-full w-64 flex-col bg-surface-dark text-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-4">
        <span className="text-sm font-semibold tracking-wide">Agent Chat</span>
      </div>

      {/* New chat button */}
      <div className="px-3 py-3">
        <button
          onClick={onCreate}
          className="flex w-full items-center gap-2 rounded-lg border border-white/20 px-3 py-2.5 text-sm transition-colors hover:bg-white/10"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New Chat
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2">
        {conversations.map(conv => (
          <ConversationItem
            key={conv.id}
            conv={conv}
            isActive={conv.id === activeId}
            onSelect={() => onSelect(conv.id)}
            onDelete={() => onDelete(conv.id)}
          />
        ))}
      </div>
    </div>
  )
}
