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
 * 恢复登录状态（关标签页 / 新开标签 / 刷新后还认得出你是谁）。
 *
 * `AuthContext` 在挂载时调用它，**不再从浏览器存储里读身份** ——
 * 那份是用户随手能改的，只有服务端回答的"你是谁"才算数。
 *
 * 未登录时后端返回 401，调用方把它当成正常结果（`user = null`），不要报错。
 */
export function fetchCurrentUser(): Promise<CurrentUser> {
  return http.get<CurrentUser>('/me')
}
