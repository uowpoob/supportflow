import { Link } from 'react-router-dom'

import { fetchConversations } from '../api/customer'
import { useAuth } from '../auth/AuthContext'
import { useApi } from '../hooks/useApi'
import { Placeholder } from '../layouts/AppLayout'
import type { JsonRecord } from '../types'

/** 侧栏里一行会话 —— 字段还没定，先把能认出来的那个当标题。 */
function conversationLabel(item: JsonRecord, index: number): string {
  for (const key of ['title', 'subject', 'conversation_no', 'order_no', 'id']) {
    const value = item[key]
    if (typeof value === 'string' || typeof value === 'number') return String(value)
  }
  return `会话 ${index + 1}`
}

/** 客户首页：快捷入口 + 左侧会话列表 + 右侧对话区。
 *  消息流等 Agent 接上再填；会话列表已经接了真实接口。 */
export function CustomerHomePage() {
  const { user } = useAuth()
  const { state, data, error, reload } = useApi(() => fetchConversations(), [])

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">你好，{user?.username}</h2>
        <p className="page-head__desc">可以查询订单、咨询售后政策、提交退款申请。</p>
      </header>

      <div className="card-grid">
        <Link className="entry-card" to="/customer/orders">
          <span className="entry-card__title">我的订单</span>
          <span className="entry-card__desc">查看订单详情与退款资格</span>
        </Link>
        <Link className="entry-card" to="/customer/refund-requests">
          <span className="entry-card__title">我的退款申请</span>
          <span className="entry-card__desc">查看申请进度与审批意见</span>
        </Link>
      </div>

      <div className="chat-layout">
        <aside className="chat-layout__side">
          <div className="side-head">会话</div>

          {state === 'loading' && (
            <div className="side-empty">
              <p className="muted">加载中…</p>
            </div>
          )}

          {state === 'error' && (
            <div className="side-empty">
              <p className="muted">{error}</p>
              <button type="button" className="btn btn--ghost btn--sm" onClick={reload}>
                重试
              </button>
            </div>
          )}

          {state === 'done' &&
            data &&
            (data.items.length === 0 ? (
              <div className="side-empty">
                <p>还没有会话</p>
                <p className="muted">
                  接口 <code>GET /api/customer/conversations</code> 已接上，后端暂无数据。
                </p>
              </div>
            ) : (
              <ul className="side-list">
                {data.items.map((item, index) => (
                  <li className="side-list__item" key={index}>
                    {conversationLabel(item, index)}
                  </li>
                ))}
              </ul>
            ))}
        </aside>

        <section className="chat-layout__main">
          <div className="chat-empty">
            <p className="chat-empty__title">对话区</p>
            <p className="muted">提问后在这里显示消息流（后续接入 SSE 流式输出）。</p>
          </div>

          <form className="composer" onSubmit={(e) => e.preventDefault()}>
            <input
              className="composer__input"
              placeholder="对话接口尚未实现，暂时无法发送"
              disabled
            />
            <button type="submit" className="btn btn--primary" disabled>
              发送
            </button>
          </form>
        </section>
      </div>

      <Placeholder title="下一步会做什么">
        <ul className="plain-list">
          <li>接入会话与消息接口，会话列表可点击切换。</li>
          <li>接 SSE 流式返回，断开后用事件 ID 或状态查询恢复，不重复执行业务操作。</li>
        </ul>
      </Placeholder>
    </div>
  )
}
