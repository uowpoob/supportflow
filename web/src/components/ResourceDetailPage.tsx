import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useApi } from '../hooks/useApi'
import type { JsonRecord } from '../types'
import { ErrorAlert, LoadingLine, RawPanel } from './Async'
import { KeyValueList } from './KeyValueList'

/**
 * 详情页的公共骨架：一个 JSON 对象 → 键值表 + 原始返回 + 返回列表的链接。
 * 后端字段没定，所以不写死字段名，直接把返回的对象摊开（见 KeyValueList）。
 */
export function ResourceDetailPage({
  title,
  desc,
  fetcher,
  backTo,
  backLabel = '返回列表',
  notice,
  actions,
  extra,
  omitKeys,
  renderExtra,
}: {
  title: string
  desc: ReactNode
  fetcher: () => Promise<JsonRecord>
  backTo: string
  backLabel?: string
  notice?: ReactNode
  /** 主数据下方的操作区（写操作按钮，目前都是禁用状态） */
  actions?: ReactNode
  /** 主数据下方的附加区块（比如订单详情下的"退款资格"） */
  extra?: ReactNode
  /** 从主数据的键值表里摘出去的字段，交给 `renderExtra` 单独渲染 */
  omitKeys?: string[]
  /** 拿到主数据后渲染的区块（比如订单详情里的商品明细表） */
  renderExtra?: (data: JsonRecord) => ReactNode
}) {
  const { state, data, error, reload } = useApi(fetcher, [])

  return (
    <div className="stack">
      <header className="page-head">
        <p className="crumbs">
          <Link className="link" to={backTo}>
            ← {backLabel}
          </Link>
        </p>
        <h2 className="page-head__title">{title}</h2>
        <p className="page-head__desc">{desc}</p>
      </header>

      {notice}

      {state === 'loading' && <LoadingLine />}
      {state === 'error' && <ErrorAlert message={error} onRetry={reload} />}
      {state === 'done' && data && (
        <>
          <KeyValueList data={data} omit={omitKeys} />
          {renderExtra?.(data)}
          <RawPanel value={data} />
        </>
      )}

      {actions}
      {extra}
    </div>
  )
}

/** 详情页里的附加区块（例如订单详情下的"退款资格"）。 */
export function AsyncSection({
  title,
  fetcher,
  notice,
}: {
  title: string
  fetcher: () => Promise<JsonRecord>
  notice?: ReactNode
}) {
  const { state, data, error, reload } = useApi(fetcher, [])

  return (
    <section className="section">
      <h3 className="section__title">{title}</h3>
      {notice}

      {state === 'loading' && <LoadingLine />}
      {state === 'error' && <ErrorAlert message={error} onRetry={reload} />}
      {state === 'done' && data && (
        <>
          <KeyValueList data={data} />
          <RawPanel value={data} label="这个区块的原始返回" />
        </>
      )}
    </section>
  )
}
