import { API_BASE } from './constants'
import type {
  CreateShareResponse,
  ShareResponse,
  SharedConversation,
  SharedEventsResponse,
  UploadFileResponse,
} from '../types/api'

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: HeadersInit = { ...(options?.headers as Record<string, string>) }
  const method = options?.method?.toUpperCase() ?? 'GET'

  if (['POST', 'PUT', 'DELETE'].includes(method) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export async function uploadFile(file: File): Promise<UploadFileResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/files/upload`, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(text || `Upload failed: ${response.status}`)
  }

  return response.json() as Promise<UploadFileResponse>
}

// ---------------------------------------------------------------------------
// Share APIs (authenticated)
// ---------------------------------------------------------------------------

export function createShare(conversationId: string): Promise<CreateShareResponse> {
  return request<CreateShareResponse>(`/conversations/${conversationId}/share`, {
    method: 'POST',
  })
}

export function deleteShare(conversationId: string): Promise<void> {
  return request<void>(`/conversations/${conversationId}/share`, {
    method: 'DELETE',
  })
}

export function getShareStatus(conversationId: string): Promise<ShareResponse> {
  return request<ShareResponse>(`/conversations/${conversationId}/share`)
}

// ---------------------------------------------------------------------------
// Memory APIs (authenticated)
// ---------------------------------------------------------------------------

export function compressConversation(conversationId: string): Promise<void> {
  return request<void>(`/conversations/${conversationId}/compress`, { method: 'POST' })
}

// ---------------------------------------------------------------------------
// Public share APIs (no credentials)
// ---------------------------------------------------------------------------

export async function fetchSharedConversation(token: string): Promise<SharedConversation> {
  const response = await fetch(`${API_BASE}/shared/${token}`)
  if (!response.ok) {
    throw new Error(`${response.status}`)
  }
  return response.json() as Promise<SharedConversation>
}

export async function fetchSharedEvents(token: string): Promise<SharedEventsResponse> {
  const response = await fetch(`${API_BASE}/shared/${token}/events`)
  if (!response.ok) {
    throw new Error(`${response.status}`)
  }
  return response.json() as Promise<SharedEventsResponse>
}
