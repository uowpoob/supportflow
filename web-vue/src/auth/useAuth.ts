import { ref } from 'vue'

import { fetchCurrentUser, login as loginApi, logout as logoutApi } from '../api/auth'
import { ApiError } from '../api/client'
import type { CurrentUser, LoginPayload } from '../types'

/**
 * 登录态**只以服务端为准**。
 *
 * 浏览器里不再存任何用户信息。前端启动时调 `GET /me` 向服务端问"我是谁"，
 * 凭证是 HttpOnly Cookie —— JS 读不到，也不需要读。
 *
 * 这样做的收益：
 * 1. 刷新页面、关掉标签再打开、在新标签里打开，都能正确恢复登录态；
 * 2. 用户改不了浏览器里的数据，也就无法把自己"变成"管理员。
 *
 * ---
 * **为什么不用 `provide` / `inject`（React 里对应的是 Context）？**
 *
 * 因为**路由守卫是全局函数，跑在组件树外面**，那里没有 `inject` 可用 ——
 * 而"这个页面该不该放你进去"恰恰必须在守卫里判断。
 * 所以状态放在模块顶层：模块只会被求值一次，下面这几个 ref 天然就是全应用单例，
 * 组件、守卫、普通 ts 文件都能直接 import 到。
 *
 * （这也是 Vue 生态里很常见的写法。需要按组件树隔离的场景才用 `provide`/`inject`，
 * 比如一个页面里要渲染两份互不干扰的数据表。）
 */

const user = ref<CurrentUser | null>(null)

/**
 * 首次向服务端确认身份期间为 true。
 *
 * ⚠️ 这段时间里 `user` **必然**是 null，但绝不能据此判断"未登录" ——
 * 否则会把"正在恢复"误判成"已登出"，一进门就把人踢回登录页。
 * 所有做身份判断的地方都必须先看这个标记。
 */
const initializing = ref(true)

/** 退出请求正在途中。界面据此禁用按钮，避免连点发出两次撤销。 */
const signingOut = ref(false)

/**
 * 恢复登录态（关标签页 / 新开标签 / 刷新后还认得出你是谁）。
 *
 * 用 Promise 缓存保证**整个应用生命周期只问服务端一次** ——
 * `main.ts` 启动时调一次，路由守卫首次导航时也会 await 它，
 * 两处共用同一个 Promise，不会发出两次 `/me`。
 */
let restorePromise: Promise<void> | null = null

export function restoreSession(): Promise<void> {
  restorePromise ??= (async () => {
    try {
      user.value = await fetchCurrentUser()
    } catch {
      // 401（没登录 / 凭证已过期 / 账号被停用）是**正常结果**，不是错误，
      // 界面上不需要报错，走登录流程即可。
      // 连不上后端时也按未登录处理 —— 真去登录时登录页会给出更具体的提示。
      user.value = null
    } finally {
      initializing.value = false
    }
  })()

  return restorePromise
}

/** 登录。成功后写入身份，调用方自己决定跳到哪。 */
async function signIn(payload: LoginPayload): Promise<CurrentUser> {
  const current = await loginApi(payload)
  user.value = current
  return current
}

/** 退出登录。**失败会抛异常**，调用方必须处理 —— 见下方实现注释。 */
async function signOut(): Promise<void> {
  signingOut.value = true
  try {
    // 真正的撤销发生在服务端：删掉 auth_sessions 那一行 + 下发过期的 Set-Cookie。
    // 前端删不掉 HttpOnly Cookie，所以这一步失败就等于**根本没退出**。
    await logoutApi()
    user.value = null
  } catch (error) {
    // 401 是例外：说明这张凭证本来就失效了（过期 / 已被别处撤销），
    // 本地按"已退出"处理是安全的，也不该把用户卡在一个无意义的错误提示里。
    if (error instanceof ApiError && error.status === 401) {
      user.value = null
      return
    }
    // 其它失败（连不上后端 / 5xx）**必须抛出去**：
    // 服务端那条会话还活着，这里若悄悄清掉本地状态，界面会宣告"退出成功"，
    // 而刷新时 `/me` 又会把人认回来 —— 用户以为退出了，凭证其实一直有效。
    throw error
  } finally {
    signingOut.value = false
  }
}

/** 拿登录态。
 *
 *  ⚠️ 和 React 版最大的区别：这里返回的是 **ref 对象本身**，不是当时的快照。
 *  模板里 `user.username` 会自动解包；`<script setup>` 里要写 `user.value`。
 *  好处是它永远是"当前值"，不需要 React 那套依赖数组去追更新。 */
export function useAuth() {
  return { user, initializing, signingOut, signIn, signOut }
}
