/** 与后端接口一一对应的类型定义。
 *  改后端 schema 时，这里同步改 —— 前端不自己造字段。 */

/** 与后端 `models/enums.py::UserRole` 保持一致 */
export type UserRole = 'customer' | 'admin'

/** 对齐后端 `models/enums.py::PaymentStatus` */
export type PaymentStatus = 'unpaid' | 'paid' | 'refunded'

/** 对齐后端 `models/enums.py::FulfillmentStatus` */
export type FulfillmentStatus = 'unshipped' | 'shipped' | 'delivered'

/** 对齐后端 `models/enums.py::RefundStatus` */
export type RefundStatus = 'pending' | 'approved' | 'rejected' | 'refunded'

/** 对齐后端 `models/enums.py::ApprovalDecision` */
export type ApprovalDecision = 'approved' | 'rejected'

/** 对齐后端 `models/enums.py::RefundExecutionStatus` */
export type RefundExecutionStatus = 'processing' | 'succeeded' | 'failed'

/** 对齐后端 `schemas/login.py::LoginRequest` */
export interface LoginPayload {
  username: string
  password: string
}

/** 对齐后端 `schemas/login.py::LoginResponse` */
export interface CurrentUser {
  id: number
  username: string
  role: UserRole
}

/**
 * 分页入参，对齐后端 `?offset=&limit=`。
 *
 * 下标签名是给"额外的过滤参数"留的（比如退款列表的 `status`）——
 * 有了它，`ResourceListPage` 的 `extraQuery` 才能把任意过滤条件拼进查询串，
 * 而不用给每个接口单独定义一套参数类型。
 */
export interface PageQuery {
  offset?: number
  limit?: number
  [key: string]: string | number | boolean | undefined
}

/**
 * 通用记录类型。
 *
 * 订单接口的响应结构还没逐字段写进 TS（列表行是弹性的），所以那边仍用它承载。
 * **退款接口已经定稿**，下面有专门的类型，不要再往这里塞。
 */
export type JsonRecord = Record<string, unknown>

/**
 * 列表接口的统一形状。
 * 认不出来就是空列表，页面再把原始 JSON 折叠出来供核对。
 */
export interface ListResult {
  items: JsonRecord[]
  total?: number
  /** 接口的原始返回，不加工，方便对着它核对字段。 */
  raw: unknown
}

// ------------------------- 退款：资格判定 -------------------------

/** 对齐后端 `schemas/refunds.py::RefundEligibilityOut` */
export interface RefundEligibility {
  eligible: boolean
  /** 机器可读的原因码：前端按它决定按钮状态，不要拿 reason_text 做判断。 */
  reason_code: string
  reason_text: string
  amount_cents: number
  delivered_at: string | null
  window_ends_at: string | null
  /** 已有进行中的申请时给出它的编号，可直接跳转 */
  existing_request_key: string | null
}

// ------------------------- 退款：申请 -------------------------

/** 对齐后端 `schemas/refunds.py::RefundOrderBrief` —— 申请所依据的订单快照 */
export interface RefundOrderBrief {
  order_no: string
  paid_amount_cents: number
  payment_status: PaymentStatus
  fulfillment_status: FulfillmentStatus
  delivered_at: string | null
}

/** 对齐后端 `schemas/refunds.py::RefundApprovalOut` */
export interface RefundApproval {
  request_key: string
  order_no: string
  decision: ApprovalDecision
  comment: string | null
  admin_username: string | null
  decided_at: string
}

/** 对齐后端 `schemas/refunds.py::RefundRecordOut` */
export interface RefundRecord {
  request_key: string
  order_no: string
  refund_no: string
  amount_cents: number
  status: RefundExecutionStatus
  attempt_count: number
  last_error: string | null
  succeeded_at: string | null
}

/** 客户侧申请列表行 —— 对齐后端 `RefundRequestBrief`，**没有**归属字段。 */
export interface MyRefundRequest {
  request_key: string
  order_no: string
  amount_cents: number
  status: RefundStatus
  created_at: string
}

/** 客户侧申请详情 —— 对齐后端 `MyRefundRequestDetail` */
export interface MyRefundRequestDetail extends MyRefundRequest {
  reason_original: string
  reason_category: string | null
  updated_at: string
  order: RefundOrderBrief
  approval: RefundApproval | null
  refund_record: RefundRecord | null
}

/** 管理侧申请列表行 —— 对齐后端 `AdminRefundRequestBrief`，**多出**归属信息。 */
export interface AdminRefundRequest extends MyRefundRequest {
  user_id: number
  username: string
}

/** 管理侧申请详情 —— 对齐后端 `AdminRefundRequestDetail` */
export interface AdminRefundRequestDetail extends AdminRefundRequest {
  reason_original: string
  reason_category: string | null
  updated_at: string
  order: RefundOrderBrief
  approval: RefundApproval | null
  refund_record: RefundRecord | null
}

/** 对齐后端 `schemas/refunds.py::RefundRequestCreate` */
export interface RefundRequestCreatePayload {
  order_no: string
  reason: string
  conversation_id?: string
}

/** 对齐后端 `schemas/refunds.py::RefundDecisionIn` */
export interface RefundDecisionPayload {
  decision: ApprovalDecision
  comment: string | null
}
