import type { JsonRecord } from '../../types'
import { humanizeKey } from './value'

/** 表格的一列。 */
export interface Column {
  key: string
  label: string
  /**
   * 自定义这一格显示什么。
   *
   * 返回**已经格式化好的文本**（`formatCents` / `labelOf` 之类）；
   * 返回空字符串会自动显示成灰色破折号 —— 见 `<CellValue>`。
   */
  render?: (row: JsonRecord) => string
  /**
   * 给这一格套一个 class，比如状态列返回 `'tag tag--warn'` 把它渲染成彩色标签。
   *
   * 为什么不把颜色塞进 `render`？因为 `render` 的契约是"只返回字符串"（见 `value.ts`），
   * 回来 JSX/VNode 会把格式化逻辑和渲染逻辑搅在一起。
   * 文案归 `render`、样式归 `cellClass`，两个函数各管一件事。
   */
  cellClass?: (row: JsonRecord) => string
}

/** 后端字段还没定，所以列由数据自己决定：取所有行出现过的键，去重保序。 */
export function deriveColumns(rows: JsonRecord[]): Column[] {
  const keys: string[] = []
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!keys.includes(key)) keys.push(key)
    }
  }
  return keys.map((key) => ({ key, label: humanizeKey(key) }))
}

/** 挑一个尽量稳定的值当列表 key；都没有就退回下标。 */
export function rowKey(row: JsonRecord, index: number): string {
  for (const key of ['id', 'order_no', 'request_key', 'username', 'no']) {
    const value = row[key]
    if (typeof value === 'string' || typeof value === 'number') return String(value)
  }
  return `row-${index}`
}
