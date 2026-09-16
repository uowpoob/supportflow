import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { login as loginApi, logout as logoutApi } from '../api/auth'
import type { CurrentUser, LoginPayload } from '../types'

/** ⚠️ 临时做法：把登录结果存在 sessionStorage 里，好让刷新页面不掉登录态。
 *
 *  这不是认证，只是"UI 记着你刚才登录过"。
 *  第 3 步后端用 HttpOnly Cookie 下发会话、并提供"当前用户"接口之后，
 *  这里要改成：初始化时调 GET /api/me 向**服务端**问"我是谁"，
 *  而不是相信浏览器里存着的那份数据（那玩意用户随手就能改）。
 */
const STORAGE_KEY = 'supportflow.currentUser'

type AuthContextValue = {
  user: CurrentUser | null
  signIn: (payload: LoginPayload) => Promise<CurrentUser>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readStoredUser(): CurrentUser | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as CurrentUser
    // 简单形状校验：结构性不对就当没登录，避免脏数据把页面搞崩
    if (typeof parsed?.id !== 'number' || typeof parsed?.username !== 'string') return null
    if (parsed.role !== 'customer' && parsed.role !== 'admin') return null
    return parsed
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(readStoredUser)

  const signIn = useCallback(async (payload: LoginPayload) => {
    const current = await loginApi(payload)
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(current))
    setUser(current)
    return current
  }, [])

  const signOut = useCallback(async () => {
    await logoutApi()
    sessionStorage.removeItem(STORAGE_KEY)
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(() => ({ user, signIn, signOut }), [user, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth 必须在 <AuthProvider> 内部使用')
  }
  return ctx
}
