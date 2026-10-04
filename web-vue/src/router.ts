import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { homePathFor } from './auth/paths'
import { restoreSession, useAuth } from './auth/useAuth'
import AppLayout from './layouts/AppLayout.vue'
import type { NavItem } from './layouts/nav'
import AdminHomePage from './pages/admin/AdminHomePage.vue'
import AdminOrderDetailPage from './pages/admin/AdminOrderDetailPage.vue'
import AdminOrdersPage from './pages/admin/AdminOrdersPage.vue'
import AdminRefundApprovalsPage from './pages/admin/AdminRefundApprovalsPage.vue'
import AdminRefundRecordsPage from './pages/admin/AdminRefundRecordsPage.vue'
import AdminRefundRequestDetailPage from './pages/admin/AdminRefundRequestDetailPage.vue'
import AdminRefundsPage from './pages/admin/AdminRefundsPage.vue'
import CustomerHomePage from './pages/customer/CustomerHomePage.vue'
import CustomerOrderDetailPage from './pages/customer/CustomerOrderDetailPage.vue'
import CustomerOrdersPage from './pages/customer/CustomerOrdersPage.vue'
import CustomerRefundRequestDetailPage from './pages/customer/CustomerRefundRequestDetailPage.vue'
import CustomerRefundRequestsPage from './pages/customer/CustomerRefundRequestsPage.vue'
import ForbiddenPage from './pages/auth/ForbiddenPage.vue'
import LoginPage from './pages/auth/LoginPage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'
import type { UserRole } from './types'

const CUSTOMER_NAV: NavItem[] = [
  { to: '/customer', label: '我的售后', icon: 'chat', end: true },
  { to: '/customer/orders', label: '我的订单', icon: 'box' },
  { to: '/customer/refund-requests', label: '我的申请', icon: 'receipt' },
]

const ADMIN_NAV: NavItem[] = [
  { to: '/admin', label: '概览', icon: 'home', end: true },
  { to: '/admin/orders', label: '订单', icon: 'box' },
  { to: '/admin/refunds', label: '退款审批', icon: 'check-badge' },
  { to: '/admin/refund-approvals', label: '审批记录', icon: 'clipboard' },
  { to: '/admin/refund-records', label: '退款流水', icon: 'wallet' },
]

/** 路由上的 `meta.role` 由下面的守卫读取 —— 这是"这个区域谁能进"的唯一声明处。 */
declare module 'vue-router' {
  interface RouteMeta {
    role?: UserRole
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginPage },

  // 客户区：必须是 customer 角色。
  // 注意页面路径与接口路径是两套：这里是页面（Vue Router 管），
  // 数据接口统一在 /api/**（后端管）。
  {
    path: '/customer',
    component: AppLayout,
    props: { nav: CUSTOMER_NAV },
    meta: { role: 'customer' },
    children: [
      { path: '', name: 'customer-home', component: CustomerHomePage },
      { path: 'orders', name: 'customer-orders', component: CustomerOrdersPage },
      { path: 'orders/:orderNo', name: 'customer-order-detail', component: CustomerOrderDetailPage },
      {
        path: 'refund-requests',
        name: 'customer-refund-requests',
        component: CustomerRefundRequestsPage,
      },
      {
        path: 'refund-requests/:requestKey',
        name: 'customer-refund-request-detail',
        component: CustomerRefundRequestDetailPage,
      },
    ],
  },

  // 管理区：必须是 admin 角色
  {
    path: '/admin',
    component: AppLayout,
    props: { nav: ADMIN_NAV },
    meta: { role: 'admin' },
    children: [
      { path: '', name: 'admin-home', component: AdminHomePage },
      { path: 'orders', name: 'admin-orders', component: AdminOrdersPage },
      { path: 'orders/:orderNo', name: 'admin-order-detail', component: AdminOrderDetailPage },
      { path: 'refunds', name: 'admin-refunds', component: AdminRefundsPage },
      {
        path: 'refunds/:requestKey',
        name: 'admin-refund-request-detail',
        component: AdminRefundRequestDetailPage,
      },
      {
        path: 'refund-approvals',
        name: 'admin-refund-approvals',
        component: AdminRefundApprovalsPage,
      },
      { path: 'refund-records', name: 'admin-refund-records', component: AdminRefundRecordsPage },
    ],
  },

  { path: '/403', name: 'forbidden', component: ForbiddenPage },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  // 翻页、切标签时回到顶部，否则从长列表点进详情会停在页面中间。
  scrollBehavior: () => ({ top: 0 }),
})

/**
 * ⚠️ 前端路由守卫只是**体验**，不是安全边界。
 *
 * 任何人打开浏览器控制台、或者直接用 curl，都能绕过这里的判断。
 * 真正的拦截必须在后端做（每个接口自己校验身份）。
 * 后端没做之前，把 /admin 页面藏起来只是"不方便"，不是"进不去"。
 *
 * ---
 * 这里替代了 React 版的 `<RequireAuth>` / `<RequireRole>` 两个包装组件：
 * React 把守卫写成"包住页面的组件"，Vue 的习惯是写成**全局前置守卫**。
 * 两者做的是同一件事，区别是守卫拿不到 `location.state`，
 * 所以"原本想去哪"改用查询参数 `?from=` 传递。
 */
router.beforeEach(async (to) => {
  // 首次导航先等 `/me` 回来，否则会拿 `user === null` 误判成"未登录"，
  // 把带着有效 Cookie 的人一脚踢回登录页。
  await restoreSession()
  const { user } = useAuth()

  // 根路径按登录态与角色分流 —— 三种去处只在这里判断一次。
  // （没有为 `/` 定义路由：它必须**先知道身份**才能决定去哪，
  //  而路由表里的静态 redirect 在守卫之前就解析掉了，读不到登录态。）
  if (to.path === '/') {
    return user.value ? homePathFor(user.value.role) : { name: 'login' }
  }

  const required = to.meta.role

  // 公开页面（/login、/403、404）直接放行。
  if (!required) return true

  // 未登录 → 跳登录页，并记住原本想去的地址。
  if (!user.value) {
    return { name: 'login', query: { from: to.fullPath } }
  }

  // 角色不符 → 显示 403 页（而不是悄悄跳走，那样用户不知道发生了什么）。
  if (user.value.role !== required) {
    return { name: 'forbidden' }
  }

  return true
})
