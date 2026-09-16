import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from './AuthContext'
import type { UserRole } from '../types'
import { ForbiddenPage } from '../pages/ForbiddenPage'

/**
 * ⚠️ 前端路由守卫只是**体验**，不是安全边界。
 *
 * 任何人打开浏览器控制台、或者直接用 curl，都能绕过这里的判断。
 * 真正的拦截必须在后端做（每个接口自己校验身份）。
 * 后端没做之前，把 /admin 页面藏起来只是"不方便"，不是"进不去"。
 */

/** 未登录 → 跳登录页，并记住原本想去的地址。 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash }} />
  }
  return <>{children}</>
}

/** 角色不符 → 显示 403 页（而不是悄悄跳走，那样用户不知道发生了什么）。 */
export function RequireRole({ role, children }: { role: UserRole; children: ReactNode }) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash }} />
  }
  if (user.role !== role) {
    return <ForbiddenPage />
  }
  return <>{children}</>
}
