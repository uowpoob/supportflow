import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { roleLabel } from '../auth/paths'

type NavItem = { to: string; label: string; end?: boolean }

/** 公共布局：顶部导航（品牌 / 主导航 / 当前用户 / 退出）+ 内容区。 */
export function AppLayout({ nav }: { nav: NavItem[] }) {
  const { user, signOut, signingOut } = useAuth()
  const navigate = useNavigate()
  const [signOutError, setSignOutError] = useState<string | null>(null)

  async function handleSignOut() {
    setSignOutError(null)
    try {
      await signOut()
      // 只有服务端真的撤销成功才离开 —— 本地状态跟着服务端走。
      navigate('/login', { replace: true })
    } catch (err) {
      // 服务端那条会话很可能还在，此时**绝不能**跳转或清空界面：
      // 否则用户以为退出了，刷新一下却又是登录态。
      // 正确做法是留在当前页、说明原因、让他重试。
      setSignOutError(err instanceof ApiError ? err.message : '退出登录失败，请重试')
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__logo" aria-hidden="true">SF</span>
          <span className="topbar__title">SupportFlow</span>
        </div>

        <nav className="topbar__nav" aria-label="主导航">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'navlink navlink--active' : 'navlink')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="topbar__user">
          {user && (
            <>
              <span className="userchip">
                <span className="userchip__name">{user.username}</span>
                <span className="userchip__role">{roleLabel(user.role)}</span>
              </span>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={handleSignOut}
                disabled={signingOut}
              >
                {signingOut ? '退出中…' : '退出'}
              </button>
            </>
          )}
        </div>
      </header>

      <main className="page">
        {signOutError && (
          <div className="alert alert--error alert--row" role="alert">
            <div>
              <div className="alert__title">退出登录失败，服务端会话可能仍然有效</div>
              <div>{signOutError}</div>
            </div>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={handleSignOut}
              disabled={signingOut}
            >
              {signingOut ? '重试中…' : '重试'}
            </button>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}

/** 尚未实现的区域的统一占位块，避免看起来像"坏了"。 */
export function Placeholder({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="placeholder">
      <h3 className="placeholder__title">{title}</h3>
      <div className="placeholder__body">{children ?? '此区域留待后续步骤填充。'}</div>
    </section>
  )
}
