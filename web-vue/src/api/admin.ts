import type { JsonRecord, ListResult, PageQuery } from '../types'
import { http } from './client'
import { encodeParam, normalizeList, pageQuery } from './list'

/**
 * 管理侧接口，与后端 `api/admin.py` 一一对应。
 *
 * ⚠️ 后端这几个接口目前**没有挂管理员鉴权**，`/admin` 前缀只是命名分区，
 * 任何人直接 curl 都能拿到数据。前端守卫拦不住 curl。
 */

/** GET /admin/orders —— 全部订单 */
export async function fetchOrders(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/orders${pageQuery(query)}`))
}

/** GET /admin/orders/{order_no} —— 订单详情（审批时核对退款依据） */
export function fetchOrder(orderNo: string): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/admin/orders/${encodeParam(orderNo)}`)
}

/** GET /admin/refund-requests —— 待办队列：`status='pending'` 的退款申请 */
export async function fetchRefundRequests(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/refund-requests${pageQuery(query)}`))
}

/** GET /admin/refund-requests/{request_key} —— 申请详情（原因原文 + 订单依据 + 已有审批） */
export function fetchRefundRequest(requestKey: string): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/admin/refund-requests/${encodeParam(requestKey)}`)
}

/**
 * POST /admin/refund-requests/{request_key}/decision —— 批准 / 拒绝。
 *
 * 审批对象是**申请**不是订单：同一订单被拒之后还能再申请，
 * 按订单号审批无法确定批的是哪一次。
 * 后端尚未实现、请求体（decision / comment）还没定，所以**页面暂时不调用它**。
 */
export function decideRefundRequest(
  requestKey: string,
  decision: 'approve' | 'reject',
  comment = '',
): Promise<JsonRecord> {
  return http.post<JsonRecord>(`/admin/refund-requests/${encodeParam(requestKey)}/decision`, {
    decision,
    comment,
  })
}

/** GET /admin/refund-approvals —— 审批记录（只有被决策过的申请才有行，审计用） */
export async function fetchRefundApprovals(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/refund-approvals${pageQuery(query)}`))
}

/** GET /admin/refund-records —— 退款执行流水（attempt_count / last_error / succeeded_at） */
export async function fetchRefundRecords(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/refund-records${pageQuery(query)}`))
}
