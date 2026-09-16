import type { JsonRecord } from '../types'
import { EmptyState } from './Async'
import { humanizeKey, renderValue } from './value'

/**
 * 一个 JSON 对象 → 键值表。
 * 后端字段还没定，所以**不写死字段名**，直接把返回的对象摊开显示。
 * 等 schema 定稿后再换成显式字段（那样能控制顺序和格式）。
 */
export function KeyValueList({ data }: { data: JsonRecord }) {
  const entries = Object.entries(data)

  if (entries.length === 0) {
    return (
      <EmptyState
        title="后端返回了空对象"
        hint="接口目前是占位实现（return result.success()），字段还没开始写。"
      />
    )
  }

  return (
    <dl className="kv">
      {entries.map(([key, value]) => (
        <div className="kv__row" key={key}>
          <dt className="kv__key">{humanizeKey(key)}</dt>
          <dd className="kv__value">{renderValue(value)}</dd>
        </div>
      ))}
    </dl>
  )
}
