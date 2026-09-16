import { fetchOrders } from '../api/admin'
import { StubNotice } from '../components/Async'
import { ResourceListPage } from '../components/ResourceListPage'

/** 全部订单 —— GET /admin/orders */
export function AdminOrdersPage() {
  return (
    <ResourceListPage
      title="订单"
      desc={
        <>
          来自 <code>GET /api/admin/orders?offset=&amp;limit=</code>
          ，含全部客户的订单。点「查看」进入详情核对退款依据。
        </>
      }
      fetcher={fetchOrders}
      detailKey="order_no"
      detailTo={(orderNo) => `/admin/orders/${orderNo}`}
      notice={
        <StubNotice>
          ⚠️ 这个接口目前<strong>没有管理员鉴权</strong>，任何人直接 curl
          都能拿到数据。前端守卫拦不住 curl，必须在后端接口上校验。
        </StubNotice>
      }
      emptyHint="后端 orders 表还没有数据。"
    />
  )
}
