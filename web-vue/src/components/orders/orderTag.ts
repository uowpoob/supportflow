import type { JsonRecord } from '../../types'
import {
  FULFILLMENT_STATUS_LABELS,
  PAYMENT_STATUS_LABELS,
  labelOf,
} from '../../labels'

/**
 * 订单相关的**两套**状态配色，单一来源（跟 `refunds/refundTag.ts` 同一个套路）：
 * `payment_status` 和 `fulfillment_status` 是两个不同的枚举，各用一张表。
 *
 * 配色语义跟 `.alert` 一致：蓝=进行中（在途）、绿=完成、黄=要注意、灰=不活跃。
 * 未支付是要用户去处理的，给黄；已退款是"钱退出去了"的终态，给灰。
 * 后端加了新状态时落到 muted，文案原样显示，不会白屏也不会显示 undefined。
 */
const PAYMENT_TONE: Record<string, string> = {
  unpaid: 'tag--warn',
  paid: 'tag--ok',
  refunded: 'tag--muted',
}

const FULFILLMENT_TONE: Record<string, string> = {
  unshipped: 'tag--muted',
  shipped: 'tag--info',
  delivered: 'tag--ok',
}

/** 只给配色类名，不含 `tag`（`.tag` 负责形状，跟 `.tag--x` 负责颜色分开）。 */
function toneOf(table: Record<string, string>, value: unknown): string {
  return table[String(value ?? '')] ?? 'tag--muted'
}

// ------------------------- 支付状态 orders.payment_status -------------------------

/** 表格 `Column.cellClass` 用：一步到位给出完整的 class。 */
export function paymentStatusCellClass(row: JsonRecord): string {
  return `tag ${toneOf(PAYMENT_TONE, row.payment_status)}`
}

/** 表格 `Column.render` 用：状态 → 中文。 */
export function paymentStatusText(row: JsonRecord): string {
  return labelOf(PAYMENT_STATUS_LABELS, row.payment_status)
}

// ------------------------- 履约状态 orders.fulfillment_status -------------------------

/** 表格 `Column.cellClass` 用：一步到位给出完整的 class。 */
export function fulfillmentStatusCellClass(row: JsonRecord): string {
  return `tag ${toneOf(FULFILLMENT_TONE, row.fulfillment_status)}`
}

/** 表格 `Column.render` 用：状态 → 中文。 */
export function fulfillmentStatusText(row: JsonRecord): string {
  return labelOf(FULFILLMENT_STATUS_LABELS, row.fulfillment_status)
}
