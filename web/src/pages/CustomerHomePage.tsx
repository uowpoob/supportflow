import { Placeholder } from '../layouts/AppLayout'
import { useAuth } from '../auth/AuthContext'

/** 客户首页：左侧会话列表 + 右侧对话区。
 *  布局先定下来，数据等 Agent 和会话接口接上再填。 */
export function CustomerHomePage() {
  const { user } = useAuth()

  return (
    <div className="stack">
      <header className="page-head">
        <h2 className="page-head__title">你好，{user?.username}</h2>
        <p className="page-head__desc">可以查询订单、咨询售后政策、提交退款申请。</p>
      </header>

      <div className="chat-layout">
        <aside className="chat-layout__side">
          <div className="side-head">会话</div>
          <div className="side-empty">
            <p>还没有会话</p>
            <p className="muted">接入 Agent 后，这里会列出历史会话。</p>
          </div>
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
