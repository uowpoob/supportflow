import { fetchMyRefundRequests } from '../api/customer'
import { ResourceListPage } from '../components/ResourceListPage'

/** 我的退款申请 —— GET /customer/refund-requests */
export function CustomerRefundRequestsPage() {
  return (
    <ResourceListPage
      title="我的退款申请"
      desc={
        <>
          来自 <code>GET /api/customer/refund-requests?offset=&amp;limit=</code>
          。点「查看」看单条申请的进度。
        </>
      }
      fetcher={fetchMyRefundRequests}
      detailKey="request_key"
      detailTo={(requestKey) => `/customer/refund-requests/${requestKey}`}
      emptyHint="后端 refund_requests 表还没有数据 —— 提交入口（POST /customer/refund-requests）也还没实现。"
    />
  )
}
