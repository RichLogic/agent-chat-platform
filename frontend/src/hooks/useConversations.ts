import { useCallback, useEffect, useState } from 'react'
import { request } from '../lib/api'
import type { Conversation, ConversationListResponse } from '../types/api'

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)

  const fetchConversations = useCallback(async () => {
    try {
      setLoading(true)
      const data = await request<ConversationListResponse>('/conversations')
      setConversations(data.items)
    } catch (err) {
      console.error('Failed to fetch conversations', err)
    } finally {
      setLoading(false)
    }
  }, [])

  async function createConversation(): Promise<Conversation> {
    const conv = await request<Conversation>('/conversations', {
      method: 'POST',
    })
    setConversations(prev => [conv, ...prev])
    return conv
  }

  async function deleteConversation(id: string) {
    await request(`/conversations/${id}`, { method: 'DELETE' })
    setConversations(prev => prev.filter(c => c.id !== id))
  }

  function updateTitle(id: string, title: string) {
    setConversations(prev =>
      prev.map(c => (c.id === id ? { ...c, title } : c)),
    )
  }

  useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  return {
    conversations,
    loading,
    createConversation,
    deleteConversation,
    updateTitle,
    refetch: fetchConversations,
  }
}
