import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'

/** 请求的三种状态。`loading` 是"还没结果"，不是"没有数据"。 */
export type AsyncState = 'loading' | 'done' | 'error'

/**
 * 统一的"发一次请求 + 管三种状态"钩子。
 *
 * 每个页面都要处理同一套流程：加载中 → 失败可重试 → 成功渲染。
 * 抽出来之后页面里只剩"拿到数据画什么"，不用每个文件都抄一遍 useState/useEffect。
 *
 * - `deps` 变化会重新请求（比如翻页）
 * - `reload()` 用于手动重试
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<AsyncState>('loading')
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false

    setState('loading')
    setError('')

    fetcher()
      .then((result) => {
        if (cancelled) return
        setData(result)
        setState('done')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : '请求失败')
        setState('error')
      })

    // 组件卸载、或依赖变化时会走到这里：把本次结果丢弃，
    // 否则"上一次的慢请求"回来会把新页面的数据覆盖掉。
    return () => {
      cancelled = true
    }
    // fetcher 每次渲染都是新函数，放进依赖会导致无限循环；
    // 所以只依赖调用方显式声明的 deps。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  return { state, data, error, reload }
}
