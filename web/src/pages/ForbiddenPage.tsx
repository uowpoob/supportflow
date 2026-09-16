import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { homePathFor } from '../auth/paths'

export function ForbiddenPage() {
  const { user } = useAuth()

  return (
    <div className="center-page">
      <div className="card center-card">
        <h2 className="center-card__title">403 没有权限</h2>
        <p className="muted">当前账号（{user?.username}）不能访问这个页面。</p>
        <Link className="btn btn--primary" to={user ? homePathFor(user.role) : '/login'}>
          回到我的首页
        </Link>
      </div>
    </div>
  )
}

export function NotFoundPage() {
  return (
    <div className="center-page">
      <div className="card center-card">
        <h2 className="center-card__title">404 页面不存在</h2>
        <p className="muted">地址写错了，或者这个页面还没做。</p>
        <Link className="btn btn--primary" to="/">
          回到首页
        </Link>
      </div>
    </div>
  )
}
