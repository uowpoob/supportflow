import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchCurrentUser, login as loginApi, logout as logoutApi } from '../api/auth'
import type { CurrentUser, LoginPayload } from '../types'

/** 登录态**只以服务端为准**。
 *
 *  浏览器里不再存任何用户信息。前端启动时调 `GET /me` 向服务端问"我是谁"，
 *  凭证是 HttpOnly Cookie —— JS 读不到，也不需要读。
 *
 *  这样做的收益：
 *  1. 刷新页面、关掉标签再打开、在新标签里打开，都能正确恢复登录态；
 *  2. 用户改不了浏览器里的数据，也就无法把自己"变成"管理员
 *     （之前把角色存在浏览器里，F12 一改就能看见管理页）。
 */
type AuthContextValue = {
  user: CurrentUser | null
  /** 首次向服务端确认身份期间为 true。
   *
   *  ⚠️ 这段时间里 `user` **必然**是 null，但绝不能据此判断"未登录" ——
   *  否则会把"正在恢复"误判成"已登出"，一进门就把人踢回登录页。
   *  所有做身份判断的地方都必须先看这个标记。 */
  initializing: boolean
  signIn: (payload: LoginPayload) => Promise<CurrentUser>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [initializing, setInitializing] = useState(true)

  // 应用启动时只问一次服务端：我手上这张 Cookie 是谁的？
  useEffect(() => {
    // React 开发模式（StrictMode）会把 effect 执行两遍，
    // 用这个标记防止先发出的那次响应回来覆盖掉后面的状态。
    let cancelled = false

    fetchCurrentUser()
      .then((current) => {
        if (!cancelled) setUser(current)
      })
      .catch(() => {
        // 401（没登录 / 凭证已过期 / 账号被停用）是**正常结果**，不是错误，
        // 界面上不需要报错，走登录流程即可。
        // 连不上后端时也按未登录处理 —— 真去登录时登录页会给出更具体的提示。
        if (!cancelled) setUser(null)
      })
      .finally(() => {
        if (!cancelled) setInitializing(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (payload: LoginPayload) => {
    const current = await loginApi(payload)
    setUser(current)
    return current
  }, [])

  const signOut = useCallback(async () => {
    try {
      await logoutApi()
    } catch {
      // 撤销请求失败（后端没起、网络断了）**不应该阻塞本地登出**：
      // 界面照样清空、照样回登录页。
      // 代价是服务端那条会话还留着 —— 它会自然过期（当前 1 小时），
      // 这也是"前端登出"和"服务端撤销"两件事的必然差别。
    } finally {
      // 无论如何都清本地状态，否则界面卡在"显示已登录、服务端却已经不认"的错位状态。
      setUser(null)
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, initializing, signIn, signOut }),
    [user, initializing, signIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth 必须在 <AuthProvider> 内部使用')
  }
  return ctx
}
