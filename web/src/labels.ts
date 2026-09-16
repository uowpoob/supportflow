/**
 * 后端枚举值 → 界面中文。
 *
 * 后端 `models/enums.py` 改了枚举，这里要一起改 —— 前端不认识后端的状态码，
 * 直接显示 `delivered` 用户看不懂，但也不能在前端"翻译"成另一套自己的状态枚举
 * （那样两边会各自演化，最后没人说得清一共有几个状态）。
 */

/** 对齐 `models/enums.py::PaymentStatus` */
export const PAYMENT_STATUS_LABELS: Record<string, string> = {
  unpaid: '未支付',
  paid: '已支付',
  refunded: '已退款',
}

/** 对齐 `models/enums.py::FulfillmentStatus` */
export const FULFILLMENT_STATUS_LABELS: Record<string, string> = {
  unshipped: '未发货',
  shipped: '已发货',
  delivered: '已签收',
}

/** 查不到就原样显示 —— 后端加了新状态时看到的是原文，而不是 "undefined"。 */
export function labelOf(labels: Record<string, string>, value: unknown): string {
  const key = String(value ?? '')
  return labels[key] ?? key
}
