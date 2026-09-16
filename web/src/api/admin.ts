import { http } from './client'
import type { JsonRecord } from './customer'

/** GET /admin/orders?offset=&limit= —— 全部订单列表 */
export function fetchOrders(offset = 0, limit = 10): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/admin/orders?offset=${offset}&limit=${limit}`)
}

/** GET /admin/refund-requests?offset=&limit= —— 待办：待审批的退款申请 */
export function fetchRefundRequests(offset = 0, limit = 10): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/admin/refund-requests?offset=${offset}&limit=${limit}`)
}

/** GET /admin/refund-approvals?offset=&limit= —— 审批记录（审计用，只看已决策的） */
export function fetchRefundApprovals(offset = 0, limit = 10): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/admin/refund-approvals?offset=${offset}&limit=${limit}`)
}

/**
 * POST /admin/refund-requests/{request_key}/decision —— 人工审批。
 *
 * 审批对象是**退款申请**（request_key），不是订单 —— 同一订单被拒之后还能再申请，
 * 按订单号无法确定批的是哪一次。
 * 后端目前是占位实现，请求体（decision / comment）待定，所以先发空对象。
 */
export function decideRefundRequest(requestKey: string): Promise<JsonRecord> {
  return http.post<JsonRecord>(`/admin/refund-requests/${requestKey}/decision`, {})
}
