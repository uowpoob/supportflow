/** 顶部导航的一项。 */
export interface NavItem {
  to: string
  label: string
  /** 只有精确停在这个地址才高亮，子路径不算（比如 `/admin` 不该在 `/admin/orders` 时点亮）。 */
  end?: boolean
}
