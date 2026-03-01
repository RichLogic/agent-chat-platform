import { API_BASE } from './constants'

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
