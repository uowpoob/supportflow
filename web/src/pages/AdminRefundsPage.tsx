import { fetchRefundRequests } from '../api/admin'
import { StubNotice } from '../components/Async'
import { ResourceListPage } from '../components/ResourceListPage'

/** 待办队列：待审批的退款申请 —— GET /admin/refund-requests */
export function AdminRefundsPage() {
  return (
    <ResourceListPage
      title="待办：退款审批"
      desc={
        <>
          来自 <code>GET /api/admin/refund-requests?offset=&amp;limit=</code> ——
          <code>refund_requests</code> 里 <code>status='pending'</code> 的申请。
        </>
      }
      fetcher={fetchRefundRequests}
      detailKey="request_key"
      detailTo={(requestKey) => `/admin/refunds/${requestKey}`}
      detailLabel="审批"
      notice={
        <StubNotice>
          这里查的是<strong>待办申请</strong>（<code>refund_requests</code>），不是审批记录（
          <code>refund_approvals</code>）。批准之前后者根本没有对应行 ——
          拿它当待办列表用会永远查出空数组。
        </StubNotice>
      }
      emptyHint="refund_requests 表还没有数据 —— 客户的提交入口（POST /customer/refund-requests）也还没实现。"
    />
  )
}
