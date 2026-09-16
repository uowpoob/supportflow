import type { ReactNode } from 'react'

/** 值 → 界面。空值给破折号，布尔给"是/否"，对象压成一行 JSON。 */
export function renderValue(value: unknown): ReactNode {
  if (value === null || value === undefined || value === '') {
    return <span className="muted">—</span>
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return <code>{JSON.stringify(value)}</code>
  return String(value)
}

/** 把 snake_case 的字段名变得好读一点：`order_no` → `order no`。后端定稿后可删。 */
export function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ')
}

/**
 * 金额：后端一律给"分"的整数，**只有在显示这一步**才换成元。
 * 千万别把换算后的浮点再传回后端 —— 0.1 + 0.2 那类误差在钱上是事故。
 */
export function formatCents(value: unknown): ReactNode {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return <span className="muted">—</span>
  }
  return `¥${(value / 100).toFixed(2)}`
}

/**
 * 时间：后端给的是带 `Z` 的 UTC ISO 串，这里转成浏览器本地时间显示。
 * 后端必须带 `Z` —— 不带的话 `new Date()` 会按本地时区解析，直接差 8 小时。
 */
export function formatDateTime(value: unknown): ReactNode {
  if (typeof value !== 'string' || value === '') {
    return <span className="muted">—</span>
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value

  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  )
}
