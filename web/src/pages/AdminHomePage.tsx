import { Link } from 'react-router-dom'

import { Placeholder } from '../layouts/AppLayout'

/** 管理员首页：四个功能区入口。 */
export function AdminHomePage() {
  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">管理后台</h2>
        <p className="page-head__desc">查看订单、处理退款审批、查审批记录与退款流水。</p>
      </header>

      <div className="card-grid">
        <Link className="entry-card" to="/admin/orders">
          <span className="entry-card__title">订单</span>
          <span className="entry-card__desc">查看全部订单，进详情核对退款依据</span>
        </Link>

        <Link className="entry-card" to="/admin/refunds">
          <span className="entry-card__title">退款审批</span>
          <span className="entry-card__desc">待办：批准或拒绝待审批的退款申请</span>
        </Link>

        <Link className="entry-card" to="/admin/refund-approvals">
          <span className="entry-card__title">审批记录</span>
          <span className="entry-card__desc">每次决策留下的凭据（审计用）</span>
        </Link>

        <Link className="entry-card" to="/admin/refund-records">
          <span className="entry-card__title">退款流水</span>
          <span className="entry-card__desc">打款执行结果与失败原因</span>
        </Link>
      </div>

      <Placeholder title="接口现状">
        <ul className="plain-list">
          <li>
            六条管理接口（<code>GET /api/admin/orders</code>、<code>/orders/&#123;order_no&#125;</code>、
            <code>/refund-requests</code>、<code>/refund-requests/&#123;request_key&#125;</code>、
            <code>/refund-approvals</code>、<code>/refund-records</code>
            ）<strong>已全部接上页面</strong>，但后端都是占位实现、返回空数据，所以页面显示的是空状态。
          </li>
          <li>
            审批（批准 / 拒绝）和客户提交申请这两个<strong>写操作</strong>只在界面上留了位置、按钮禁用，
            等请求体定稿再打开。
          </li>
          <li>
            ⚠️ 后端这些管理接口<strong>还没有鉴权</strong>：任何人都能直接 curl 调用。
            前端守卫挡不住 curl，尽快在接口上加管理员校验。
          </li>
        </ul>
      </Placeholder>
    </div>
  )
}
