import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import { useConversations } from '../../hooks/useConversations'
import { useStreamChat } from '../../hooks/useStreamChat'
import Sidebar from './Sidebar'
import ChatArea from '../chat/ChatArea'
import ChatInput from '../chat/ChatInput'
import TraceView from '../replay/TraceView'
import type { FileInfo } from '../../types/api'

export default function ChatLayout() {
  const { user, logout } = useAuth()
  const { conversations, createConversation, deleteConversation, updateTitle } = useConversations()
  const { messages, isStreaming, sendMessage, loadMessages, setMessages, onTitleUpdate, stopStreaming } = useStreamChat()
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [traceRunId, setTraceRunId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

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

  async function handleSelectConversation(id: string) {
    setActiveConvId(id)
    setTraceRunId(null)
    await loadMessages(id)
  }

  async function handleNewChat() {
    const conv = await createConversation()
    setActiveConvId(conv.id)
    setMessages([])
    setTraceRunId(null)
  }

  async function handleDeleteConversation(id: string) {
    await deleteConversation(id)
    if (activeConvId === id) {
      setActiveConvId(null)
      setMessages([])
      setTraceRunId(null)
    }
  }

  async function handleSend(content: string, fileIds?: string[], files?: FileInfo[]) {
    if (!activeConvId) {
      const conv = await createConversation()
      setActiveConvId(conv.id)
      await sendMessage(conv.id, content, fileIds, files)
    } else {
      await sendMessage(activeConvId, content, fileIds, files)
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
