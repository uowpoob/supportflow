import type {
  AdminRefundRequestDetail,
  JsonRecord,
  ListResult,
  PageQuery,
  RefundDecisionPayload,
} from '../types'
import { http } from './client'
import { encodeParam, normalizeList, pageQuery } from './list'

/**
 * 管理侧接口，与后端 `api/admin/*.py` 一一对应。
 *
 * 准入由后端 `admin/__init__.py` 挂的 `require_admin` 负责 ——
 * 前端路由守卫只是体验，拦不住 curl。
 *
 * 三张表的分工（写代码时最容易搞混的地方）：
 * - `/admin/refund-requests` 是**客户提交的申请**，待办就是它的 `?status=pending`
 * - `/admin/refund-approvals` 是**管理员做出的决策**，只有被决策过的申请才有行
 * - `/admin/refund-records` 是**真正退过钱的流水**
 */

/** GET /admin/orders —— 全部订单 */
export async function fetchOrders(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/orders${pageQuery(query)}`))
}

/** GET /admin/orders/{order_no} —— 订单详情（审批时核对退款依据） */
export function fetchOrder(orderNo: string): Promise<JsonRecord> {
  return http.get<JsonRecord>(`/admin/orders/${encodeParam(orderNo)}`)
}

/**
 * GET /admin/refund-requests —— 退款申请队列。
 *
 * 传 `{ status: 'pending' }` 就是待办列表；不传就是全部。
 */
export async function fetchRefundRequests(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/refund-requests${pageQuery(query)}`))
}

/** GET /admin/refund-requests/{request_key} —— 申请详情（原因原文 + 订单依据 + 已有审批） */
export function fetchRefundRequest(requestKey: string): Promise<AdminRefundRequestDetail> {
  return http.get<AdminRefundRequestDetail>(
    `/admin/refund-requests/${encodeParam(requestKey)}`,
  )
}

/**
 * POST /admin/refund-requests/{request_key}/decision —— 批准 / 拒绝。
 *
 * 审批对象是**申请**不是订单：同一订单被拒之后还能再申请，
 * 按订单号审批无法确定批的是哪一次。
 *
 * `decision` 用后端的枚举值 `approved` / `rejected`，不要自己发明
 * `approve` / `reject` —— 两套写法迟早会在某处对不上。
 *
 * **批准会立刻执行模拟退款**（改申请状态、写流水、把订单标成已退款），
 * 全在同一个数据库事务里完成。
 */
export function decideRefundRequest(
  requestKey: string,
  payload: RefundDecisionPayload,
): Promise<AdminRefundRequestDetail> {
  return http.post<AdminRefundRequestDetail>(
    `/admin/refund-requests/${encodeParam(requestKey)}/decision`,
    payload,
  )
}

/** GET /admin/refund-approvals —— 审批记录（只有被决策过的申请才有行，审计用） */
export async function fetchRefundApprovals(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/refund-approvals${pageQuery(query)}`))
}

/** GET /admin/refund-records —— 退款执行流水（attempt_count / last_error / succeeded_at） */
export async function fetchRefundRecords(query: PageQuery = {}): Promise<ListResult> {
  return normalizeList(await http.get<unknown>(`/admin/refund-records${pageQuery(query)}`))
}
