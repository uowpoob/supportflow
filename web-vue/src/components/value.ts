/**
 * 值 → 界面文本。
 *
 * ⚠️ 和 React 版最大的区别：这里**一律返回字符串**，不再返回 JSX 片段。
 * React 里可以 `return <span className="muted">—</span>` 把样式也一起返回，
 * Vue 的函数里做不到（要返回 VNode 就得用 h()，把简单的格式化搞复杂了）。
 * 所以空值统一返回空字符串，由 `<CellValue>` 这一个组件负责"空 → 灰色破折号"，
 * 表格和键值表两处共用同一套显示规则。
 */

/** 空值给空串（调用方显示成破折号），布尔给"是/否"，对象压成一行 JSON。 */
export function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value) ?? ''
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
export function formatCents(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return ''
  return `¥${(value / 100).toFixed(2)}`
}

/**
 * 时间：后端给的是带 `Z` 的 UTC ISO 串，这里转成浏览器本地时间显示。
 * 后端必须带 `Z` —— 不带的话 `new Date()` 会按本地时区解析，直接差 8 小时。
 */
export function formatDateTime(value: unknown): string {
  if (typeof value !== 'string' || value === '') return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value

  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  )
}
