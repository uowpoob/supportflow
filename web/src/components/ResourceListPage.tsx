import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useApi } from '../hooks/useApi'
import type { JsonRecord, ListResult, PageQuery } from '../types'
import { EmptyState, ErrorAlert, LoadingLine, RawPanel } from './Async'
import type { Column } from './DataTable'
import { DataTable, deriveColumns } from './DataTable'
import { Pager } from './Pager'

const DEFAULT_LIMIT = 10

/**
 * 列表页的公共骨架：请求 → 四种状态（加载中 / 失败可重试 / 空 / 有数据）→ 分页 → 原始返回。
 *
 * 几个列表页都在用它，每个页面自己只剩三件事：标题、请求哪个接口、点哪一列进详情。
 * 想看单个页面的效果，先看 `AdminOrdersPage.tsx`（最短）。
 */
export function ResourceListPage({
  title,
  desc,
  fetcher,
  columns,
  detailKey,
  detailTo,
  detailLabel = '查看',
  notice,
  emptyHint,
}: {
  title: string
  desc: ReactNode
  fetcher: (query: PageQuery) => Promise<ListResult>
  /** 显式指定列；不传就按数据里的字段自动生成 */
  columns?: Column[]
  /** 用行里的哪个字段拼详情地址，比如 `order_no` */
  detailKey?: string
  detailTo?: (value: string) => string
  detailLabel?: string
  /** 表格上方的提示块（比如"接口未鉴权"的警告） */
  notice?: ReactNode
  emptyHint?: ReactNode
}) {
  const [offset, setOffset] = useState(0)
  const { state, data, error, reload } = useApi(
    () => fetcher({ offset, limit: DEFAULT_LIMIT }),
    [offset],
  )

  const rows = data?.items ?? []
  const baseColumns = columns ?? deriveColumns(rows)
  const cols: Column[] =
    detailKey && detailTo
      ? [
          ...baseColumns,
          {
            key: '__detail__',
            label: '操作',
            render: (row: JsonRecord) => {
              const value = row[detailKey]
              if (typeof value !== 'string' && typeof value !== 'number') {
                return <span className="muted">—</span>
              }
              return (
                <Link className="link" to={detailTo(String(value))}>
                  {detailLabel}
                </Link>
              )
            },
          },
        ]
      : baseColumns

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">{title}</h2>
        <p className="page-head__desc">{desc}</p>
      </header>

      {notice}

      {state === 'loading' && <LoadingLine />}
      {state === 'error' && <ErrorAlert message={error} onRetry={reload} />}
      {state === 'done' && data && (
        <>
          {rows.length === 0 ? (
            <EmptyState title="没有数据" hint={emptyHint} />
          ) : (
            <>
              <DataTable rows={rows} columns={cols} />
              <Pager
                offset={offset}
                limit={DEFAULT_LIMIT}
                count={rows.length}
                total={data.total}
                onChange={setOffset}
              />
            </>
          )}
          <RawPanel value={data.raw} />
        </>
      )}
    </div>
  )
}
