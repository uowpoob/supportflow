import type { CurrentUser, LoginPayload } from '../types'
import { http } from './client'

/** POST /login —— 对齐后端 `api/login.py`。成功返回 {id, username, role}。 */
export function login(payload: LoginPayload): Promise<CurrentUser> {
  return http.post<CurrentUser>('/login', payload)
}

/**
 * 退出登录 —— POST /logout，对齐后端 `api/logout.py`。
 *
 * 必须发这个请求，前端自己删不掉 Cookie：它是 HttpOnly 的，JS 读不到也改不了。
 * 后端收到后会做两件事：删掉服务端会话记录（真正的撤销）+ 下发过期的 Set-Cookie。
 *
 * 后端设计成幂等：没登录、凭证已过期都会返回 200，所以这里一般不会抛错。
 */
export function logout(): Promise<void> {
  return http.post<void>('/logout')
}

/**
 * 恢复登录状态（刷新页面后还认得出你是谁）。
 * 后端 `GET /me` 已实现，但**尚未接入** `AuthContext` ——
 * 那边目前仍从浏览器临时存储里读身份（见 AuthContext.tsx 顶部注释）。
 * 接入时要同时给 user 加一个 loading 态，否则 `/me` 返回前会被守卫误判成未登录。
 */
export function fetchCurrentUser(): Promise<CurrentUser> {
  return http.get<CurrentUser>('/me')
}
