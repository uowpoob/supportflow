import type { UserRole } from '../types'

/** 每个角色登录后该落到哪个页面 —— 只在一处定义，避免到处写 `/user` `/admin` 字符串。 */
export function homePathFor(role: UserRole): string {
  return role === 'admin' ? '/admin' : '/customer'
}

/** 回到本角色的站内页面，保留查询参数和锚点；其他地址回首页。 */
export function returnPathFor(role: UserRole, from: unknown): string {
  const home = homePathFor(role)
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//') || from.includes('\\')) {
    return home
  }
  try {
    const target = new URL(from, 'https://supportflow.invalid')
    if (target.pathname === home || target.pathname.startsWith(`${home}/`)) {
      return target.pathname + target.search + target.hash
    }
  } catch {
    // 非法地址不影响登录。
  }
  return home
}

export function roleLabel(role: UserRole): string {
  return role === 'admin' ? '管理员' : '客户'
}
