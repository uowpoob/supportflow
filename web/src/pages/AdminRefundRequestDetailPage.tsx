import { useParams } from 'react-router-dom'

import { fetchRefundRequest } from '../api/admin'
import { StubNotice } from '../components/Async'
import { ResourceDetailPage } from '../components/ResourceDetailPage'

/** 退款申请详情（管理侧）—— GET /admin/refund-requests/{request_key} */
export function AdminRefundRequestDetailPage() {
  const { requestKey = '' } = useParams()

  return (
    <ResourceDetailPage
      title={`退款申请 ${requestKey}`}
      desc={
        <>
          来自 <code>GET /api/admin/refund-requests/{requestKey}</code>
          ：客户填写的原因原文、订单依据、已有审批。
        </>
      }
      fetcher={() => fetchRefundRequest(requestKey)}
      backTo="/admin/refunds"
      backLabel="返回待办列表"
      actions={
        <section className="section">
          <h3 className="section__title">审批</h3>
          <StubNotice>
            批准 / 拒绝调{' '}
            <code>POST /api/admin/refund-requests/{requestKey}/decision</code>，后端尚未实现。实现时要在
            <strong>同一个事务里</strong>做两件事：改 <code>refund_requests.status</code>，
            并新增一行 <code>refund_approvals</code>（<code>admin_id</code> 只能取自登录态，
            绝不接受请求参数）。
          </StubNotice>
          <div className="page-actions">
            <button type="button" className="btn btn--primary" disabled>
              批准
            </button>
            <button type="button" className="btn btn--ghost" disabled>
              拒绝
            </button>
            <span className="muted">等决策接口定稿后启用</span>
          </div>
        </section>
      }
    />
  )
}
