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

// ------------------------- 会话与消息 -------------------------

/** 对齐 `agents/graph/state.py::RetrievalStatus` —— 本轮检索的结果状态 */
export type RetrievalStatus = 'not_requested' | 'unavailable' | 'empty' | 'ready'

export type WebSearchStatus = 'not_requested' | 'unavailable' | 'empty' | 'ready'

export interface WebSource {
  title: string
  url: string
}

/** 对齐后端 `schemas/conversations.py::ChatMessageOut` —— 只有这两种角色 */
export type ChatRole = 'user' | 'assistant'

/**
 * 一条可展示的消息。
 *
 * 后端 `_public_messages` 已经滤掉了 system 提示、工具调用和工具返回，
 * 到了前端只会是用户的文字或助手的答复 —— **不需要再判断别的角色**。
 */
export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
}

/** 对齐后端 `schemas/conversations.py::ConversationOut` —— 会话的"壳"，不含消息 */
export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

/** 对齐后端 `schemas/conversations.py::ConversationPage` */
export interface ConversationPage {
  items: Conversation[]
  total: number
  offset: number
  limit: number
}

/** 一页历史消息及当前运行快照；刷新后用它恢复草稿、来源和输入框状态。 */
export interface ConversationMessages {
  conversation_id: string
  items: ChatMessage[]
  total: number
  offset: number
  limit: number
  /** 这个会话当前的图状态；新会话没有 checkpoint 时同样是 `completed` */
  status: MessageTurnStatus
  /** `waiting_approval` 时是那张暂停的申请编号；否则为 null */
  pending_request_key: string | null
  /** 本进程里这个会话是否正有一轮在跑（流式输出尚未结束）；刷新后靠它认出"正在回复" */
  running: boolean
  active_turn: { user_message: ChatMessage; assistant_text: string } | null
  retrieval_status: RetrievalStatus
  retrieved_sources: RetrievedSource[]
  web_search_status: WebSearchStatus
  web_sources: WebSource[]
  run_error: string | null
}

/** 对齐后端 `schemas/conversations.py::RetrievedSourceOut` —— 本轮召回的候选片段 */
export interface RetrievedSource {
  document_id: string
  chunk_id: string
  title: string
  source: string
  section: string | null
  score: number | null
}

/**
 * 对齐后端 `schemas/conversations.py::MessageTurnOut::status`。
 *
 * - `completed`：这一轮跑完了，可以继续提问。
 * - `waiting_approval`：Agent 提交了退款申请，整张图**暂停**在那里等管理员决策；
 *   这期间再发消息后端会返回 409，界面必须自己把输入框锁上。
 */
export type MessageTurnStatus = 'completed' | 'waiting_approval'

/**
 * 对齐后端 `schemas/conversations.py::MessageTurnOut` —— 一轮对话的增量返回。
 *
 * `messages` 里**包含本轮用户自己那条消息**：拿到之后整段接在消息列表尾部即可，
 * 不要再单独把用户输入也插一遍，否则显示两遍。
 */
export interface MessageTurn {
  conversation_id: string
  messages: ChatMessage[]
  /** 本轮结束时图是停住了还是在等审批 */
  status: MessageTurnStatus
  /** `waiting_approval` 时是那张暂停的申请编号；否则为 null */
  pending_request_key: string | null
  retrieval_status: RetrievalStatus
  retrieved_sources: RetrievedSource[]
  web_search_status: WebSearchStatus
  web_sources: WebSource[]
  /** 首轮后自动生成的标题；非首轮或生成失败时为 null */
  title?: string | null
}

/** 对齐后端 `schemas/conversations.py::MessageCreate` —— 只提交这一句话 */
export interface MessageCreatePayload {
  content: string
}

/** 对齐后端 `schemas/conversations.py::ConversationTitle` —— 只提交新标题 */
export interface ConversationTitlePayload {
  title: string
}

// ------------------------- 流式（SSE） -------------------------

/**
 * 流式连接里收到的一帧。
 *
 * 后端的成功事件（错误事件在 API 层转成 ApiError）：
 * - `delta`：模型正在吐的一段字，逐帧追加到气泡里。
 * - `done`：本轮跑完，带的 `turn` 跟非流式接口返回的**是同一个结构**。
 *
 * `unknown` 是"后端发了新事件、前端还不认识"的情况 —— 丢掉就好，
 * 不要猜它的含义。加上它是因为以后可能加 `tool` / `sources` 之类的事件，
 * 老前端遇到新事件不该炸。
 */
export type StreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; turn: MessageTurn }
  | { type: 'unknown'; event: string }
