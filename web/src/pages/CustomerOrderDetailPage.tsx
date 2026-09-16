import { useParams } from 'react-router-dom'

import { fetchMyOrder, fetchRefundEligibility } from '../api/customer'
import { StubNotice } from '../components/Async'
import { AsyncSection, ResourceDetailPage } from '../components/ResourceDetailPage'

/** 订单详情 —— GET /customer/orders/{order_no} + 退款资格子接口 */
export function CustomerOrderDetailPage() {
  const { orderNo = '' } = useParams()

  return (
    <ResourceDetailPage
      title={`订单 ${orderNo}`}
      desc={
        <>
          来自 <code>GET /api/customer/orders/{orderNo}</code>，含商品明细。
        </>
      }
      fetcher={() => fetchMyOrder(orderNo)}
      backTo="/customer/orders"
      backLabel="返回我的订单"
      actions={
        <section className="section">
          <h3 className="section__title">提交退款申请</h3>
          <StubNotice>
            提交入口是 <code>POST /api/customer/refund-requests</code>
            ，后端尚未实现、请求体（退款原因、金额）也还没定，所以按钮先禁用。
          </StubNotice>
          <div className="page-actions">
            <button type="button" className="btn btn--primary" disabled>
              提交退款申请
            </button>
            <span className="muted">等 POST /customer/refund-requests 定稿后启用</span>
          </div>
        </section>
      }
      extra={
        <AsyncSection
          title="退款资格"
          fetcher={() => fetchRefundEligibility(orderNo)}
          notice={
            <StubNotice>
              这是<strong>只读</strong>判定：只回答「能不能退、为什么不能」，不写库、不占额度，
              可以反复调用。真正的资格规则还没实现。
            </StubNotice>
          }
        />
      }
    />
  )
}
