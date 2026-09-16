/**
 * 分页条。后端用 offset/limit。
 * 拿不到总数时，用"本页是否满页"来推断有没有下一页 —— 不够准，但不会点不动。
 */
export function Pager({
  offset,
  limit,
  count,
  total,
  onChange,
}: {
  offset: number
  limit: number
  count: number
  total?: number
  onChange: (offset: number) => void
}) {
  const hasPrev = offset > 0
  const hasNext = total !== undefined ? offset + count < total : count >= limit
  const range = count === 0 ? '本页没有数据' : `第 ${offset + 1}–${offset + count} 条`

  return (
    <div className="pager">
      <span className="muted">
        {range}
        {total !== undefined && ` / 共 ${total} 条`}
      </span>
      <div className="pager__actions">
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          disabled={!hasPrev}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          上一页
        </button>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          disabled={!hasNext}
          onClick={() => onChange(offset + limit)}
        >
          下一页
        </button>
      </div>
    </div>
  )
}
