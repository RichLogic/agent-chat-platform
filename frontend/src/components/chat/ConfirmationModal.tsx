import { useCallback, useEffect, useState } from 'react'
import type { ApprovalRequestData } from '../../types/events'

interface ConfirmationModalProps {
  approval: ApprovalRequestData | null
  onResolve: (approvalId: string, approved: boolean) => void
}

const RISK_LABELS: Record<string, string> = {
  write: 'Write Operation',
  destructive: 'Destructive Operation',
  admin: 'Admin Operation',
}

const RISK_COLORS: Record<string, string> = {
  write: 'text-amber-600',
  destructive: 'text-red-600',
  admin: 'text-red-700',
}

export default function ConfirmationModal({ approval, onResolve }: ConfirmationModalProps) {
  const [loading, setLoading] = useState(false)

  const handleResolve = useCallback(async (approved: boolean) => {
    if (!approval) return
    setLoading(true)
    try {
      await fetch(`/api/approvals/${approval.approval_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
        credentials: 'include',
      })
      onResolve(approval.approval_id, approved)
    } catch (err) {
      console.error('Failed to resolve approval', err)
    } finally {
      setLoading(false)
    }
  }, [approval, onResolve])

  // Close on Escape
  useEffect(() => {
    if (!approval) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleResolve(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [approval, handleResolve])

  if (!approval) return null

  const riskLabel = RISK_LABELS[approval.risk_level] || approval.risk_level
  const riskColor = RISK_COLORS[approval.risk_level] || 'text-amber-600'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100">
            <svg className="h-5 w-5 text-amber-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </div>
          <div>
            <h3 className="text-base font-semibold text-text">Tool Confirmation</h3>
            <span className={`text-xs font-medium ${riskColor}`}>{riskLabel}</span>
          </div>
        </div>

        {/* Tool info */}
        <div className="mb-4 rounded-lg border border-border bg-surface p-3">
          <div className="mb-2 text-sm font-medium text-text">{approval.tool_name}</div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-text-muted">
            {JSON.stringify(approval.arguments, null, 2)}
          </pre>
        </div>

        {/* Reason */}
        {approval.reason && (
          <p className="mb-4 text-xs text-text-muted">{approval.reason}</p>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => handleResolve(false)}
            disabled={loading}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-text transition-colors hover:bg-surface disabled:opacity-50"
          >
            Deny
          </button>
          <button
            onClick={() => handleResolve(true)}
            disabled={loading}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? 'Processing...' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  )
}
