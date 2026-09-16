import type { ReactNode } from 'react'

import type { JsonRecord } from '../types'
import { humanizeKey, renderValue } from './value'

export interface Column {
  key: string
  label: string
  render?: (row: JsonRecord) => ReactNode
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

/** 挑一个尽量稳定的值当 React key；都没有就退回下标。 */
function rowKey(row: JsonRecord, index: number): string {
  for (const key of ['id', 'order_no', 'request_key', 'username', 'no']) {
    const value = row[key]
    if (typeof value === 'string' || typeof value === 'number') return String(value)
  }
  return `row-${index}`
}

export function DataTable({ rows, columns }: { rows: JsonRecord[]; columns?: Column[] }) {
  const cols = columns ?? deriveColumns(rows)

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {cols.map((col) => (
              <th key={col.key}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {cols.map((col) => (
                <td key={col.key}>{col.render ? col.render(row) : renderValue(row[col.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
