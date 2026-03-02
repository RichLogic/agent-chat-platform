import { useCallback, useState } from 'react'
import { createShare, deleteShare, getShareStatus } from '../lib/api'
import type { ShareResponse } from '../types/api'

export function useShare() {
  const [shareInfo, setShareInfo] = useState<ShareResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const checkShare = useCallback(async (conversationId: string) => {
    try {
      const data = await getShareStatus(conversationId)
      setShareInfo(data)
    } catch {
      setShareInfo(null)
    }
  }, [])

  const share = useCallback(async (conversationId: string) => {
    setLoading(true)
    try {
      const data = await createShare(conversationId)
      setShareInfo({ shared: true, share_token: data.share_token, share_url: data.share_url })
      return data.share_url
    } finally {
      setLoading(false)
    }
  }, [])

  const unshare = useCallback(async (conversationId: string) => {
    setLoading(true)
    try {
      await deleteShare(conversationId)
      setShareInfo({ shared: false })
    } finally {
      setLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setShareInfo(null)
  }, [])

  return {
    shareInfo,
    loading,
    checkShare,
    share,
    unshare,
    reset,
  }
}
