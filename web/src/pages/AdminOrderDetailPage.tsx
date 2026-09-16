import { useParams } from 'react-router-dom'

import { fetchOrder } from '../api/admin'
import { ResourceDetailPage } from '../components/ResourceDetailPage'

/** 订单详情（管理侧）—— GET /admin/orders/{order_no}，审批时核对退款依据用 */
export function AdminOrderDetailPage() {
  const { orderNo = '' } = useParams()

  return (
    <ResourceDetailPage
      title={`订单 ${orderNo}`}
      desc={
        <>
          来自 <code>GET /api/admin/orders/{orderNo}</code>，含商品明细与实付金额。
        </>
      }
      fetcher={() => fetchOrder(orderNo)}
      backTo="/admin/orders"
      backLabel="返回订单列表"
    />
  )
}
