import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchCurrentUser, login as loginApi, logout as logoutApi } from '../api/auth'
import { ApiError } from '../api/client'
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
  /** 退出请求正在途中。界面据此禁用按钮，避免连点发出两次撤销。 */
  signingOut: boolean
  signIn: (payload: LoginPayload) => Promise<CurrentUser>
  /** 退出登录。**失败会抛异常**，调用方必须处理 —— 见下方实现注释。 */
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [signingOut, setSigningOut] = useState(false)

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
    setSigningOut(true)
    try {
      // 真正的撤销发生在服务端：删掉 auth_sessions 那一行 + 下发过期的 Set-Cookie。
      // 前端删不掉 HttpOnly Cookie，所以这一步失败就等于**根本没退出**。
      await logoutApi()
      setUser(null)
    } catch (error) {
      // 401 是例外：说明这张凭证本来就失效了（过期 / 已被别处撤销），
      // 本地按"已退出"处理是安全的，也不该把用户卡在一个无意义的错误提示里。
      if (error instanceof ApiError && error.status === 401) {
        setUser(null)
        return
      }
      // 其它失败（连不上后端 / 5xx）**必须抛出去**：
      // 服务端那条会话还活着，这里若悄悄清掉本地状态，界面会宣告"退出成功"，
      // 而刷新时 `/me` 又会把人认回来 —— 用户以为退出了，凭证其实一直有效。
      throw error
    } finally {
      setSigningOut(false)
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ user, initializing, signingOut, signIn, signOut }),
    [user, initializing, signingOut, signIn, signOut],
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
