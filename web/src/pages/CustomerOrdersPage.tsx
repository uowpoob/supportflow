import { fetchMyOrders } from '../api/customer'
import { ResourceListPage } from '../components/ResourceListPage'

/** 我的订单 —— GET /customer/orders */
export function CustomerOrdersPage() {
  return (
    <ResourceListPage
      title="我的订单"
      desc={
        <>
          来自 <code>GET /api/customer/orders?offset=&amp;limit=</code>
          ，只包含当前登录账号自己的订单（身份取自 Cookie，不是请求参数）。
        </>
      }
      fetcher={fetchMyOrders}
      detailKey="order_no"
      detailTo={(orderNo) => `/customer/orders/${orderNo}`}
      emptyHint="后端 orders 表还没有数据。等 scripts/seed.py 把测试订单造出来，这里就有内容了。"
    />
  )
}
