import { useRef, useState, type KeyboardEvent } from 'react'
import { uploadFile } from '../../lib/api'
import type { FileInfo } from '../../types/api'

interface PendingFile {
  file: File
  uploading: boolean
  uploaded?: FileInfo & { id: string }
  error?: string
}

interface ChatInputProps {
  onSend: (content: string, fileIds?: string[], files?: FileInfo[]) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState('')
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files) return

    for (const file of Array.from(files)) {
      if (file.type !== 'application/pdf') continue

      const pending: PendingFile = { file, uploading: true }
      setPendingFiles(prev => [...prev, pending])

      try {
        const result = await uploadFile(file)
        setPendingFiles(prev =>
          prev.map(p =>
            p.file === file
              ? { ...p, uploading: false, uploaded: { id: result.id, original_filename: result.original_filename, size_bytes: result.size_bytes, page_count: result.page_count } }
              : p,
          ),
        )
      } catch (err) {
        setPendingFiles(prev =>
          prev.map(p =>
            p.file === file
              ? { ...p, uploading: false, error: (err as Error).message }
              : p,
          ),
        )
      }
    }

    // Reset file input so same file can be selected again
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function removeFile(index: number) {
    setPendingFiles(prev => prev.filter((_, i) => i !== index))
  }

  function handleSend() {
    const trimmed = value.trim()
    const uploadedFiles = pendingFiles.filter(p => p.uploaded)
    if ((!trimmed && uploadedFiles.length === 0) || disabled) return

    const fileIds = uploadedFiles.map(p => p.uploaded!.id)
    const files = uploadedFiles.map(p => p.uploaded!)
    onSend(trimmed || '请查看我上传的文件', fileIds.length > 0 ? fileIds : undefined, files.length > 0 ? files : undefined)
    setValue('')
    setPendingFiles([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleInput() {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`
    }
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes}B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
  }

  const hasUploaded = pendingFiles.some(p => p.uploaded)

  return (
    <div className="border-t border-border bg-surface px-4 py-3">
      <div className="mx-auto max-w-3xl">
        {/* Pending files */}
        {pendingFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {pendingFiles.map((pf, i) => (
              <div
                key={i}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs ${
                  pf.error
                    ? 'border-red-300 bg-red-50 text-red-700'
                    : pf.uploading
                      ? 'border-border bg-surface-dim text-text-muted'
                      : 'border-border bg-surface-dim text-text'
                }`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span className="max-w-[150px] truncate">{pf.file.name}</span>
                {pf.uploading && (
                  <span className="animate-pulse">uploading...</span>
                )}
                {pf.uploaded && (
                  <span className="text-text-muted">{formatSize(pf.uploaded.size_bytes)}</span>
                )}
                {pf.error && <span>failed</span>}
                <button
                  onClick={() => removeFile(i)}
                  className="ml-0.5 text-text-muted hover:text-text"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          {/* File upload button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border text-text-muted transition-colors hover:bg-surface-dim hover:text-text disabled:opacity-40"
            title="Upload PDF"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />

          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder="Type a message..."
            disabled={disabled}
            rows={1}
            className="max-h-[200px] min-h-[44px] flex-1 resize-none rounded-xl border border-border bg-surface-dim px-4 py-3 text-sm text-text outline-none transition-colors placeholder:text-text-muted focus:border-primary focus:ring-1 focus:ring-primary disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={disabled || (!value.trim() && !hasUploaded)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-white transition-colors hover:bg-primary-dark disabled:opacity-40"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
