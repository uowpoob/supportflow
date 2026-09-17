import type {
  JsonRecord,
  ListResult,
  MyRefundRequestDetail,
  PageQuery,
  RefundEligibility,
  RefundRequestCreatePayload,
} from '../types'
import { http } from './client'
import { encodeParam, normalizeList, pageQuery } from './list'

/**
 * 客户侧接口，与后端 `api/customer/*.py` 一一对应。
 *
 * 注意这里的函数**一律不接受 user_id 之类参数** —— 身份由 Cookie 决定。
 * 能传身份就等于能看别人的订单/申请，这是设计上的硬边界。
 *
 * 退款相关的函数返回的是**具体类型**而不是 `JsonRecord`：
 * 后端结构已经定稿（`schemas/refunds.py`），字段名再靠猜就会掩盖真实的拼写错误。
 */

/** GET /customer/orders —— 我的订单列表 */
export async function fetchMyOrders(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/customer/orders${pageQuery(query)}`))
}

/** GET /customer/orders/{order_no} —— 订单详情（含商品明细） */
export function fetchMyOrder(orderNo: string): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/customer/orders/${encodeParam(orderNo)}`)
}

/** GET /customer/orders/{order_no}/refund-eligibility —— 能不能退（只读，不写库、不占额度） */
export function fetchRefundEligibility(orderNo: string): Promise<RefundEligibility> {
  return http.get<RefundEligibility>(`/customer/orders/${encodeParam(orderNo)}/refund-eligibility`)
}

/**
 * POST /customer/refund-requests —— 提交退款申请（整条写流程的唯一入口）。
 *
 * 请求体里**没有金额**也没有用户 —— 金额取订单实付、身份取 Cookie。
 * 重复提交是幂等的：后端会把既有那条返回回来，不会新建第二笔。
 */
export function submitRefundRequest(
  payload: RefundRequestCreatePayload,
): Promise<MyRefundRequestDetail> {
  return http.post<MyRefundRequestDetail>('/customer/refund-requests', payload)
}

/** GET /customer/refund-requests —— 我提交过的退款申请 */
export async function fetchMyRefundRequests(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/customer/refund-requests${pageQuery(query)}`))
}

/** GET /customer/refund-requests/{request_key} —— 单条申请进度（状态 + 审批意见 + 退款结果） */
export function fetchMyRefundRequest(requestKey: string): Promise<MyRefundRequestDetail> {
  return http.get<MyRefundRequestDetail>(`/customer/refund-requests/${encodeParam(requestKey)}`)
}

/** GET /customer/conversations —— 我的对话会话（Agent 接上之后才会有内容） */
export async function fetchConversations(): Promise<ListResult> {
  return normalizeList(await http.get<unknown>('/customer/conversations'))
}
