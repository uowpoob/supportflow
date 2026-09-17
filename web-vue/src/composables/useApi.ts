import { ref, shallowRef, watchEffect } from 'vue'

import { ApiError } from '../api/client'

/** 请求的三种状态。`loading` 是"还没结果"，不是"没有数据"。 */
export type AsyncState = 'loading' | 'done' | 'error'

/**
 * 统一的"发一次请求 + 管三种状态"的 composable。
 *
 * 每个页面都要处理同一套流程：加载中 → 失败可重试 → 成功渲染。
 * 抽出来之后页面里只剩"拿到数据画什么"，不用每个文件都抄一遍 ref/watchEffect。
 *
 * ---
 * **和 React 版的 `useApi(fetcher, deps)` 有个关键差别：这里不需要传 `deps`。**
 *
 * React 里 `useEffect` 要知道"什么时候该重新请求"，只能靠你手写依赖数组；
 * 而 `fetcher` 每次渲染都是新函数，放进依赖会无限循环，所以必须由调用方
 * 把真正的依赖（比如 `offset`）再声明一遍 —— 写漏了就是"翻页没反应"。
 *
 * Vue 的 `watchEffect` 会**自动记住这次执行期间读到了哪些响应式数据**：
 * `() => fetcher({ offset: offset.value, limit: 10 })` 里读了 `offset`，
 * 以后 `offset` 一变就自动重跑。少写一样东西，也少一处会写错的地方。
 *
 * 副作用是"依赖变成隐式的了" —— 排查"为什么又发了一次请求"时，
 * 看 `fetcher` 里读了哪些 `ref` 就是答案。
 */
export function useApi<T>(fetcher: () => Promise<T>) {
  const state = ref<AsyncState>('loading')
  const data = shallowRef<T | null>(null)
  const error = ref('')
  /** 每次自增 = "再请求一次"，供失败重试使用。 */
  const nonce = ref(0)

  // 请求序号：慢请求回来时如果已经有更新的请求发出去了，
  // 就把这次的结果丢掉，否则旧数据会盖掉新页面的内容。
  // （React 版用 effect 的清理函数里那个 `cancelled` 标记做同一件事。）
  let seq = 0

  watchEffect(() => {
    // 显式读一下 nonce：它变了就是"用户点了重试"。
    // 不读的话它就不是这个 effect 的依赖，reload 会毫无反应。
    void nonce.value

    const mySeq = ++seq
    state.value = 'loading'
    error.value = ''

    fetcher()
      .then((result) => {
        if (mySeq !== seq) return
        data.value = result
        state.value = 'done'
      })
      .catch((err: unknown) => {
        if (mySeq !== seq) return
        error.value = err instanceof ApiError ? err.message : '请求失败'
        state.value = 'error'
      })
  })

  /** 手动重试。 */
  function reload() {
    nonce.value += 1
  }

  return { state, data, error, reload }
}
