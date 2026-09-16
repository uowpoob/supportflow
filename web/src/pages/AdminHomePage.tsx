import { Link } from 'react-router-dom'

import { Placeholder } from '../layouts/AppLayout'

/** 管理员首页：订单、退款审批两个入口。 */
export function AdminHomePage() {
  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">管理后台</h2>
        <p className="page-head__desc">查看订单、处理退款审批。</p>
      </header>

      <div className="card-grid">
        <Link className="entry-card" to="/admin/orders">
          <span className="entry-card__title">订单</span>
          <span className="entry-card__desc">按状态与时间查看订单列表</span>
        </Link>

        <Link className="entry-card" to="/admin/refunds">
          <span className="entry-card__title">退款审批</span>
          <span className="entry-card__desc">批准或拒绝待审批的退款申请</span>
        </Link>
      </div>

      <Placeholder title="接口现状">
        <ul className="plain-list">
          <li>
            <code>GET /api/admin/orders</code>、<code>GET /api/admin/refund-requests</code>
            （待办队列）、<code>POST /api/admin/refund-requests/&#123;request_key&#125;/decision</code>
            （审批）已占位，但目前都返回空数据，页面会把原始返回原样展示出来，方便确认前后端已打通。
          </li>
          <li>
            ⚠️ 后端这几个管理接口**还没有鉴权**：现在任何人直接调用都能拿到数据。
            前端守卫挡不住 curl，尽快在接口上加管理员校验。
          </li>
        </ul>
      </Placeholder>
    </div>
  )
}
