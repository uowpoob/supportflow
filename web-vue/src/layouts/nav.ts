/** 顶部导航的一项。 */
export interface NavItem {
  to: string
  label: string
  /** 图标名，对应 `AppIcon.vue` 里那张字典表。不给就只显示文字。 */
  icon?: string
  /** 只有精确停在这个地址才高亮，子路径不算（比如 `/admin` 不该在 `/admin/orders` 时点亮）。 */
  end?: boolean
}
