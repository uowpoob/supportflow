import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { returnPathFor } from '../auth/paths'

interface LocationState {
  from?: string
}

export function LoginPage() {
  const { user, signIn } = useAuth()
  const location = useLocation()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [details, setDetails] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  // 恢复原访问地址；没有原地址或角色不匹配时进入自己的首页。
  if (user) {
    return <Navigate to={returnPathFor(user.role, (location.state as LocationState | null)?.from)} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setDetails([])
    setSubmitting(true)

    try {
      // 用户状态更新后由上面的 Navigate 统一跳转，避免两个跳转互相覆盖。
      await signIn({ username, password })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
        setDetails(err.details)
      } else {
        setError('登录失败，请稍后再试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={handleSubmit} noValidate>
        <div className="login-card__head">
          <span className="topbar__logo" aria-hidden="true">SF</span>
          <h1 className="login-card__title">SupportFlow</h1>
          <p className="login-card__subtitle">智能售后工单助手</p>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            <div className="alert__title">{error}</div>
            {details.length > 0 && (
              <ul className="alert__list">
                {details.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <label className="field">
          <span className="field__label">用户名</span>
          <input
            className="field__input"
            name="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>

        <label className="field">
          <span className="field__label">密码</span>
          <input
            className="field__input"
            name="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
          {submitting ? '登录中…' : '登录'}
        </button>

        <p className="login-card__hint">
          演示账号：<code>admin / 123456</code>（管理员）；客户账号 <code>customer1</code>、<code>customer2</code>
        </p>
      </form>
    </div>
  )
}
