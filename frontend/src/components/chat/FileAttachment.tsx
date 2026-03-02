import type { FileInfo } from '../../types/api'

interface FileAttachmentProps {
  files: FileInfo[]
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

export default function FileAttachment({ files }: FileAttachmentProps) {
  if (!files.length) return null

  return (
    <div className="mb-1.5 flex flex-wrap gap-1.5">
      {files.map(f => (
        <div
          key={f.id}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-surface-dim px-2.5 py-1.5 text-xs text-text"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-red-500">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
          <span className="max-w-[200px] truncate">{f.original_filename}</span>
          <span className="text-text-muted">{formatSize(f.size_bytes)}</span>
          {f.page_count != null && (
            <span className="text-text-muted">{f.page_count}p</span>
          )}
        </div>
      ))}
    </div>
  )
}
