import { useEffect, useState } from 'react'

import { fetchRefundRequests } from '../api/admin'
import { ApiError } from '../api/client'

/** 退款审批页：先只做"能读到数据"这一步，审批按钮等接口请求体定下来再加。 */
export function AdminRefundsPage() {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [data, setData] = useState<unknown>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false

    fetchRefundRequests(0, 10)
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
        <h2 className="page-head__title">退款审批</h2>
        <p className="page-head__desc">
          待办数据来自 <code>GET /api/admin/refund-requests?offset=0&amp;limit=10</code>
        </p>
      </header>

      <div className="alert alert--warn">
        审批接口是 <code>POST /api/admin/refund-requests/&#123;request_key&#125;/decision</code>，
        后端目前只占位、返回空数据。等请求体（decision / comment）定下来，再加"批准 / 拒绝"按钮。
        审批通过后会写入 <code>refund_approvals</code>，可在"审批记录"里查（接口已占位）。
      </div>

      {state === 'loading' && <p className="muted">加载中…</p>}
      {state === 'error' && <div className="alert alert--error">{message}</div>}
      {state === 'done' && <pre className="codeblock">{JSON.stringify(data, null, 2)}</pre>}
    </div>
  )
}
