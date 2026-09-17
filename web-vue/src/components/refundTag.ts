import type { JsonRecord } from '../types'
import {
  REFUND_EXECUTION_STATUS_LABELS,
  REFUND_STATUS_LABELS,
  labelOf,
} from '../labels'

/**
 * 退款相关的**两套**状态配色，单一来源：表格列、详情页徽章都从这里取，
 * 免得同一个"待审批"在列表里是黄的、在详情里是蓝的。
 *
 * 为什么要两套：`refund_requests.status` 和 `refund_records.status` 是**两个不同的枚举**，
 * 只是碰巧都叫 `status`。前者是"审批走到哪一步"（pending/approved/rejected/refunded），
 * 后者是"打款执行结果"（processing/succeeded/failed）。用一张表硬合并的话，
 * `approved` 会落到 muted、`failed` 会显示成中文"失败"却配蓝色 —— 那种错很难一眼看出来。
 *
 * 配色按"这个状态意味着什么"选，不是按顺序。
 * 后端加了新状态时落到 muted，文案原样显示，不会白屏也不会显示 undefined。
 */
const REQUEST_TONE: Record<string, string> = {
  pending: 'tag--warn',
  approved: 'tag--info',
  refunded: 'tag--ok',
  rejected: 'tag--danger',
}

const EXECUTION_TONE: Record<string, string> = {
  processing: 'tag--info',
  succeeded: 'tag--ok',
  failed: 'tag--danger',
}

/** 只给配色类名，不含 `tag`（`.tag` 负责形状，跟 `.tag--x` 负责颜色分开）。 */
function toneOf(table: Record<string, string>, value: unknown): string {
  return table[String(value ?? '')] ?? 'tag--muted'
}

// ------------------------- 申请状态 refund_requests.status -------------------------

/**
 * 详情页里 `<span class="tag" :class="refundStatusTone(x)">` 用。
 * 跟表格的 `refundStatusCellClass` 取的是同一张表 —— 同一个状态在两处不会变色。
 */
export function refundStatusTone(value: unknown): string {
  return toneOf(REQUEST_TONE, value)
}

/** 表格 `Column.cellClass` 用：一步到位给出完整的 class。 */
export function refundStatusCellClass(row: JsonRecord): string {
  return `tag ${toneOf(REQUEST_TONE, row.status)}`
}

/** 表格 `Column.render` 用：状态 → 中文。 */
export function refundStatusText(row: JsonRecord): string {
  return labelOf(REFUND_STATUS_LABELS, row.status)
}

// ------------------------- 执行状态 refund_records.status -------------------------

/** `RefundStatusTag` 之外的地方要配色时用它（例如流水页的状态列）。 */
export function refundExecutionTone(value: unknown): string {
  return toneOf(EXECUTION_TONE, value)
}

export function refundExecutionCellClass(row: JsonRecord): string {
  return `tag ${toneOf(EXECUTION_TONE, row.status)}`
}

export function refundExecutionText(row: JsonRecord): string {
  return labelOf(REFUND_EXECUTION_STATUS_LABELS, row.status)
}
