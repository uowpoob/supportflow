import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'

import { useAuth } from '../auth/AuthContext'
import { roleLabel } from '../auth/paths'

type NavItem = { to: string; label: string; end?: boolean }

/** 公共布局：顶部导航（品牌 / 主导航 / 当前用户 / 退出）+ 内容区。 */
export function AppLayout({ nav }: { nav: NavItem[] }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  async function handleSignOut() {
    await signOut()
    navigate('/login', { replace: true })
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
              <button type="button" className="btn btn--ghost" onClick={handleSignOut}>
                退出
              </button>
            </>
          )}
        </div>
      </header>

      <main className="page">
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
