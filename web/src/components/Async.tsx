import type { ReactNode } from 'react'

/** 加载中。 */
export function LoadingLine({ label = '加载中…' }: { label?: string }) {
  return <p className="muted">{label}</p>
}

/** 请求失败：带重试按钮，否则用户只能刷整页。 */
export function ErrorAlert({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert alert--error alert--row">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  )
}

/**
 * 请求成功但没有数据。
 * 必须和"后端还没实现"分开表述 —— 否则分不清是页面坏了还是本来就没内容。
 */
export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="empty-state">
      <p className="empty-state__title">{title}</p>
      {hint && <p className="empty-state__hint">{hint}</p>}
    </div>
  )
}

/** 给"后端待实现"用的统一说明块。 */
export function StubNotice({ children }: { children: ReactNode }) {
  return <div className="alert alert--warn">{children}</div>
}

/** 后端响应结构未定稿期间，把原始返回折叠出来，方便对着字段改页面。 */
export function RawPanel({ value, label = '接口原始返回' }: { value: unknown; label?: string }) {
  return (
    <details className="raw">
      <summary className="raw__summary">{label}</summary>
      <pre className="codeblock">{JSON.stringify(value, null, 2) ?? 'null'}</pre>
    </details>
  )
}
