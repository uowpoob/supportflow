import type { JsonRecord } from '../types'
import { EmptyState } from './Async'
import { humanizeKey, renderValue } from './value'

/**
 * 一个 JSON 对象 → 键值表。
 * 后端字段还没定，所以**不写死字段名**，直接把返回的对象摊开显示。
 * 等 schema 定稿后再换成显式字段（那样能控制顺序和格式）。
 *
 * `omit` 用来把某些字段摘出去单独渲染 —— 比如订单详情里的 `items` 是个数组，
 * 摊在键值表里只会变成一行挤不下的 JSON，它该有自己的表格。
 */
export function KeyValueList({ data, omit = [] }: { data: JsonRecord; omit?: string[] }) {
  const entries = Object.entries(data).filter(([key]) => !omit.includes(key))

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
