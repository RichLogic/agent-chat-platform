import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import { useConversations } from '../../hooks/useConversations'
import { useStreamChat } from '../../hooks/useStreamChat'
import { useShare } from '../../hooks/useShare'
import Sidebar from './Sidebar'
import ChatArea from '../chat/ChatArea'
import ChatInput from '../chat/ChatInput'
import TraceView from '../replay/TraceView'
import { compressConversation } from '../../lib/api'
import type { FileInfo } from '../../types/api'

export default function ChatLayout() {
  const { user, logout } = useAuth()
  const { conversations, createConversation, deleteConversation, updateTitle } = useConversations()
  const { messages, isStreaming, sendMessage, loadMessages, setMessages, onTitleUpdate, stopStreaming } = useStreamChat()
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [traceRunId, setTraceRunId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const { shareInfo, loading: shareLoading, share, reset: resetShare } = useShare()
  const [showSharePopover, setShowSharePopover] = useState(false)
  const [copied, setCopied] = useState(false)
  const sharePopoverRef = useRef<HTMLDivElement>(null)

  // Agent mode toggle — persisted in localStorage
  const [agentMode, setAgentMode] = useState(() => localStorage.getItem('agent_mode') === 'true')

  function toggleAgentMode() {
    setAgentMode(prev => {
      const next = !prev
      localStorage.setItem('agent_mode', String(next))
      return next
    })
  }

  const handleTitleUpdate = useCallback(
    (title: string) => {
      if (activeConvId) {
        updateTitle(activeConvId, title)
      }
    },
    [activeConvId, updateTitle],
  )

  useEffect(() => {
    onTitleUpdate.current = handleTitleUpdate
  }, [handleTitleUpdate, onTitleUpdate])

  // Close share popover on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (sharePopoverRef.current && !sharePopoverRef.current.contains(e.target as Node)) {
        setShowSharePopover(false)
      }
    }
    if (showSharePopover) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showSharePopover])

  async function handleShareClick() {
    if (!activeConvId) return
    if (showSharePopover) {
      setShowSharePopover(false)
      return
    }
    const url = await share(activeConvId)
    if (url) {
      setShowSharePopover(true)
      setCopied(false)
    }
  }

  async function handleCopyShareUrl() {
    if (shareInfo?.share_url) {
      await navigator.clipboard.writeText(shareInfo.share_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 3000)
    }
  }

  async function handleSelectConversation(id: string) {
    // Trigger memory compression for the conversation we're leaving
    if (activeConvId && activeConvId !== id) {
      compressConversation(activeConvId).catch(() => {})
    }
    setActiveConvId(id)
    setTraceRunId(null)
    setShowSharePopover(false)
    resetShare()
    await loadMessages(id)
  }

  async function handleNewChat() {
    const conv = await createConversation()
    setActiveConvId(conv.id)
    setMessages([])
    setTraceRunId(null)
    setShowSharePopover(false)
    resetShare()
  }

  async function handleDeleteConversation(id: string) {
    await deleteConversation(id)
    if (activeConvId === id) {
      setActiveConvId(null)
      setMessages([])
      setTraceRunId(null)
      setShowSharePopover(false)
      resetShare()
    }
  }

  async function handleSend(content: string, fileIds?: string[], files?: FileInfo[]) {
    if (!activeConvId) {
      const conv = await createConversation()
      setActiveConvId(conv.id)
      await sendMessage(conv.id, content, fileIds, files, agentMode)
    } else {
      await sendMessage(activeConvId, content, fileIds, files, agentMode)
    }
  }

  return (
    <div className="flex h-full">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed z-30 h-full transition-transform md:relative md:z-0 md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Sidebar
          conversations={conversations}
          activeId={activeConvId}
          onSelect={id => {
            handleSelectConversation(id)
            setSidebarOpen(false)
          }}
          onCreate={() => {
            handleNewChat()
            setSidebarOpen(false)
          }}
          onDelete={handleDeleteConversation}
        />
      </div>

      {/* Main area */}
      <div className="flex flex-1 flex-col">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface-dim md:hidden"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <h1 className="text-sm font-medium text-text">
              {activeConvId
                ? conversations.find(c => c.id === activeConvId)?.title ?? 'Chat'
                : 'Agent Chat'}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            {/* Agent mode toggle */}
            <button
              onClick={toggleAgentMode}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
                agentMode
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-text-muted hover:bg-surface-dim'
              }`}
              title={agentMode ? 'Agent 模式已开启 (Plan & Execute)' : 'Agent 模式已关闭'}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z" />
                <path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z" />
              </svg>
              Agent
              {/* Toggle indicator */}
              <span
                className={`inline-block h-3 w-6 rounded-full transition-colors ${
                  agentMode ? 'bg-primary' : 'bg-gray-300'
                } relative`}
              >
                <span
                  className={`absolute top-0.5 h-2 w-2 rounded-full bg-white transition-transform ${
                    agentMode ? 'translate-x-3.5' : 'translate-x-0.5'
                  }`}
                />
              </span>
            </button>

            {/* Share button */}
            {activeConvId && !isStreaming && (
              <div className="relative" ref={sharePopoverRef}>
                <button
                  onClick={handleShareClick}
                  disabled={shareLoading}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-dim disabled:opacity-50"
                >
                  <span className="flex items-center gap-1.5">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="18" cy="5" r="3" />
                      <circle cx="6" cy="12" r="3" />
                      <circle cx="18" cy="19" r="3" />
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                    </svg>
                    Share
                  </span>
                </button>
                {showSharePopover && shareInfo?.share_url && (
                  <div className="absolute right-0 top-full z-50 mt-2 w-72 rounded-lg border border-border bg-white p-3 shadow-lg">
                    <p className="mb-2 text-xs font-medium text-text">Share link</p>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={shareInfo.share_url}
                        className="flex-1 rounded border border-border bg-surface-dim px-2 py-1 text-xs text-text"
                      />
                      <button
                        onClick={handleCopyShareUrl}
                        className="shrink-0 rounded bg-primary px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-primary/90"
                      >
                        {copied ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {isStreaming && (
              <button
                onClick={stopStreaming}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface-dim"
              >
                Stop
              </button>
            )}
            {user && (
              <div className="flex items-center gap-2">
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={user.display_name}
                    className="h-7 w-7 rounded-full"
                  />
                ) : (
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-white">
                    {user.display_name?.charAt(0).toUpperCase() ?? 'U'}
                  </div>
                )}
                <button
                  onClick={logout}
                  className="text-xs text-text-muted transition-colors hover:text-text"
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </header>

        {/* Chat area */}
        <ChatArea
          messages={messages}
          isStreaming={isStreaming}
          onViewTrace={runId => setTraceRunId(traceRunId === runId ? null : runId)}
        />

        {/* Trace view */}
        {traceRunId && (
          <TraceView runId={traceRunId} onClose={() => setTraceRunId(null)} />
        )}

        {/* Input */}
        <ChatInput onSend={handleSend} disabled={isStreaming} />
      </div>
    </div>
  )
}
