import type {
  Conversation,
  ConversationMessages,
  ConversationPage,
  JsonRecord,
  ListResult,
  MessageCreatePayload,
  MessageTurn,
  MyRefundRequestDetail,
  PageQuery,
  RefundEligibility,
  RefundRequestCreatePayload,
  StreamEvent,
} from '../types'
import { ApiError, http, openPostStream } from './client'
import { encodeParam, normalizeList, pageQuery } from './list'
import { parseSseChunk, type SseEvent } from './sse'

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

/**
 * 会话接口，对应后端 `api/customer/conversations.py`。
 *
 * 字段全部照 `schemas/conversations.py` 写死，不再返回 `JsonRecord` ——
 * 会话这块的结构已经定稿（见 `docs/conversation-api.md`），
 * 靠猜字段只会把拼写错误拖到运行期才暴露。
 */

/** POST /customer/conversations —— 新建会话（只建壳，不调模型、不生成消息） */
export function createConversation(title?: string): Promise<Conversation> {
  // 不传标题时后端用默认的"新会话"；这里不替它编一个标题。
  return http.post<Conversation>('/customer/conversations', title === undefined ? {} : { title })
}

/** GET /customer/conversations —— 我的会话，按最近活动时间倒序 */
export function fetchConversations(query: PageQuery = {}): Promise<ConversationPage> {
  return http.get<ConversationPage>(`/customer/conversations${pageQuery(query)}`)
}

/**
 * GET /customer/conversations/{id}/messages —— 历史消息。
 *
 * ⚠️ `offset=0` 拿的是**最早**的那些，不是最新的；要最新一段得先知道 total
 * 再倒着算，或者像首页那样一次性把 limit 拉满。
 */
export function fetchConversationMessages(
  conversationId: string,
  query: PageQuery = {},
): Promise<ConversationMessages> {
  return http.get<ConversationMessages>(
    `/customer/conversations/${encodeParam(conversationId)}/messages${pageQuery(query)}`,
  )
}

/**
 * POST /customer/conversations/{id}/messages —— 发一条消息。
 *
 * 非流式：这个请求要等到整轮跑完（模型 + 工具 + 检索）才返回，
 * 中间没有任何输出，所以界面上得自己显示"正在回复"。
 * 返回的 `messages` 里**包含刚发的那条用户消息**。
 */
export function sendConversationMessage(conversationId: string, content: string): Promise<MessageTurn> {
  const payload: MessageCreatePayload = { content }
  return http.post<MessageTurn>(
    `/customer/conversations/${encodeParam(conversationId)}/messages`,
    payload,
  )
}

/**
 * POST /customer/conversations/{id}/messages/stream —— 流式发一条消息。
 *
 * 后端一个 SSE 连接里只发两种事件（见 `api/customer/conversations.py`）：
 *
 *     event: delta   data: {"text": "增量文字"}
 *     event: done    data: {…整个 MessageTurnOut…}
 *
 * 也就是说：`delta` 是模型正在往外吐的字，`done` 是本轮跑完后**跟非流式接口
 * 一模一样的那个对象**。前端不用自己拼结果，拿到 `done` 直接当非流式的结果用。
 *
 * 注意点：
 * - 只有 `delta` 里的字是模型已经说出口的；**工具调用、检索过程都没有事件**，
 *   所以"发出去 → 第一个字到"之间仍然是一段没有反馈的空白。
 * - 出错时后端不会走 HTTP 状态码（响应的 200 已经发出去了），而是直接断流；
 *   调用方要靠"stream 结束但没等到 done"来判断这一轮失败。
 * - 传 `signal` 可以中途取消（组件卸载时用），取消后后端也会跟着停。
 */
export async function* streamConversationMessage(
  conversationId: string,
  content: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const payload: MessageCreatePayload = { content }
  const response = await openPostStream(
    `/customer/conversations/${encodeParam(conversationId)}/messages/stream`,
    payload,
  )
  if (signal !== undefined) {
    // 已经取消过了就直接结束，别白读一遍。
    if (signal.aborted) throw new DOMException('已取消', 'AbortError')
  }

  const reader = response.body?.getReader()
  if (reader === undefined) {
    throw new ApiError(response.status, '后端没有返回流式响应体')
  }

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })

      const { events, carry } = parseSseChunk(buffer)
      buffer = carry
      for (const item of events) {
        yield toStreamEvent(item)
      }
    }

    // 收尾：最后一段可能没有以空行结尾。
    buffer += decoder.decode()
    const { events } = parseSseChunk(buffer, true)
    for (const item of events) {
      yield toStreamEvent(item)
    }
  } finally {
    // 取消或异常时别把连接挂着。
    await reader.cancel().catch(() => undefined)
  }
}

/** SSE 事件 -> 业务事件；认不出来的事件直接丢掉（不猜、不报错）。 */
function toStreamEvent(item: SseEvent): StreamEvent {
  if (item.event === 'delta') {
    const payload = JSON.parse(item.data) as { text?: unknown }
    return { type: 'delta', text: typeof payload.text === 'string' ? payload.text : '' }
  }
  if (item.event === 'done') {
    return { type: 'done', turn: JSON.parse(item.data) as MessageTurn }
  }
  return { type: 'unknown', event: item.event }
}
