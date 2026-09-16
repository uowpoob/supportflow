import type { PageQuery } from '../types'
import { http } from './client'

/** 后端这些接口目前返回空信封（`result.success()`），等业务数据接上再补类型。 */
export type JsonRecord = Record<string, unknown>

/** GET /customer/conversations —— 我的对话会话列表（后端待实现） */
export function fetchConversations(): Promise<JsonRecord> {
  return http.get<JsonRecord>('/customer/conversations')
}

/** GET /customer/orders —— 我的订单（后端待实现） */
export function fetchMyOrders(query: PageQuery = {}): Promise<JsonRecord> {
  const params = new URLSearchParams()
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  const suffix = params.toString()
  return http.get<JsonRecord>(`/customer/orders${suffix ? `?${suffix}` : ''}`)
}
