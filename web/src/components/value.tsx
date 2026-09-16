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
