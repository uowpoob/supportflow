/** 统一的请求封装：一处处理后端地址、Cookie、错误格式。
 *  页面里不要直接写 fetch —— 否则每个页面都要重复解析错误。 */

/** 开发期由 vite.config.ts 的 proxy 把 /api 转发到 FastAPI；
 *  生产环境由反向代理（nginx / Compose）做同样的转发。
 *  要用别的地址时在 web/.env.local 里设 VITE_API_BASE_URL。 */
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** 后端统一的成功信封（见 src/supportflow/schemas/result.py）。 */
interface Envelope<T> {
  code?: string
  message?: string
  data?: T
}

/** 所有请求失败都抛这个，页面只认 status 和 message。 */
export class ApiError extends Error {
  readonly status: number
  /** 422 时后端会给出字段级错误，逐条列出来便于定位。 */
  readonly details: string[]

  constructor(status: number, message: string, details: string[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

/** 后端可能返回 {code, message, data} 信封，也可能直接返回业务对象。
 *  两种都能解析，等信封方案最终定了再删掉多余分支。 */
function unwrap<T>(body: unknown): T {
  if (body !== null && typeof body === 'object' && 'data' in body) {
    const envelope = body as Envelope<T>
    if (envelope.data !== undefined) {
      return envelope.data
    }
  }
  return body as T
}

/** 把后端返回的各式错误压成一句人话 + 若干细节。
 *
 *  原则：**后端已经说明原因就照用**。同一个状态码在不同接口含义不同 ——
 *  `/login` 的 401 是"用户名或密码错误"，`/me`、`/logout` 的 401 是"会话已失效"，
 *  `/customer/orders/{order_no}` 的 404 是"订单不存在"（不是"接口不存在"）。
 *  按状态码一刀切会把它们说成同一个意思，纯属误导。
 *  只有后端**没给** `detail`（或只给了 "Not Found" 这类无信息量的英文）时才按状态码兜底。 */
function parseError(status: number, body: unknown): ApiError {
  let message = `请求失败（HTTP ${status}）`
  let backendSaidWhy = false
  const details: string[] = []

  if (body !== null && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail

    if (typeof detail === 'string' && detail.trim() !== '') {
      message = detail
      backendSaidWhy = true
    } else if (Array.isArray(detail)) {
      // FastAPI 校验错误：detail: [{loc: ["body","username"], msg: "..."}]
      message = '提交的内容不符合要求'
      backendSaidWhy = true
      for (const item of detail) {
        if (item !== null && typeof item === 'object' && 'msg' in item) {
          const loc = (item as { loc?: unknown[] }).loc ?? []
          const field = loc.filter((p) => p !== 'body').join('.')
          const msg = String((item as { msg: unknown }).msg)
          details.push(field ? `${field}：${msg}` : msg)
        }
      }
    }
  }

  // ⚠️ 404 这行原来是无条件覆盖的，会把后端那句"订单不存在"盖成
  // "接口不存在（后端可能还没实现）" —— 越权访问时看到的正是这句，误导排查方向。
  // 现在跟 401/403 一样：后端说了原因就照用，没说才兜底。
  // （后端路由现在是齐的，404 只可能表示"这条数据查不到"。）
  if (status >= 500) {
    message = '服务端出错，请查看后端日志'
  } else if (!backendSaidWhy && status === 404) {
    message = '接口不存在（后端可能还没实现）'
  } else if (!backendSaidWhy && status === 401) {
    message = '需要登录后才能访问该接口'
  } else if (!backendSaidWhy && status === 403) {
    message = '当前账号没有访问该接口的权限'
  }

  return new ApiError(status, message, details)
}

/**
 * 发一次请求。
 * - `credentials: 'include'` 是给第 3 步准备的：后端一旦用 Set-Cookie 下发会话，
 *   浏览器就会自动带上，前端不需要（也读不到）凭证本身。
 */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...init.headers,
      },
      credentials: 'include',
    })
  } catch {
    throw new ApiError(0, '连不上后端，请确认 FastAPI 已启动（默认 127.0.0.1:8000）')
  }

  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!response.ok) {
    throw parseError(response.status, body)
  }
  return unwrap<T>(body)
}

export const http = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, payload?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: payload === undefined ? undefined : JSON.stringify(payload),
    }),
}
