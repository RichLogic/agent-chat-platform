import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react'
import { request } from '../lib/api'
import type { User } from '../types/api'

export interface AuthContextValue {
  user: User | null
  loading: boolean
  login: () => void
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: () => {},
  logout: async () => {},
  checkAuth: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const checkAuth = useCallback(async () => {
    try {
      const data = await request<User>('/auth/me')
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  function login() {
    request<{ url: string }>('/auth/login')
      .then(({ url }) => {
        window.location.href = url
      })
      .catch(console.error)
  }

  async function logout() {
    await request('/auth/logout', { method: 'POST' })
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  )
}
