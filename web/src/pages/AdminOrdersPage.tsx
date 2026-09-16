import { useEffect, useState } from 'react'

import { fetchOrders } from '../api/admin'
import { ApiError } from '../api/client'

/** 订单页：这一步只验证"请求链路通不通"，把后端原始返回展示出来。 */
export function AdminOrdersPage() {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [data, setData] = useState<unknown>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false

    fetchOrders(0, 10)
      .then((result) => {
        if (cancelled) return
        setData(result)
        setState('done')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setMessage(err instanceof ApiError ? err.message : '请求失败')
        setState('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">订单</h2>
        <p className="page-head__desc">
          数据来自 <code>GET /api/admin/orders?offset=0&amp;limit=10</code>
        </p>
      </header>

      {state === 'loading' && <p className="muted">加载中…</p>}
      {state === 'error' && <div className="alert alert--error">{message}</div>}
      {state === 'done' && (
        <>
          <div className="alert alert--info">
            后端返回如下。等列表数据结构定下来，这里换成表格。
          </div>
          <pre className="codeblock">{JSON.stringify(data, null, 2)}</pre>
        </>
      )}
    </div>
  )
}
