import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth/AuthContext'
import { AuthLoading, RequireRole } from './auth/guards'
import { homePathFor } from './auth/paths'
import { AppLayout } from './layouts/AppLayout'
import { AdminHomePage } from './pages/AdminHomePage'
import { AdminOrderDetailPage } from './pages/AdminOrderDetailPage'
import { AdminOrdersPage } from './pages/AdminOrdersPage'
import { AdminRefundApprovalsPage } from './pages/AdminRefundApprovalsPage'
import { AdminRefundRecordsPage } from './pages/AdminRefundRecordsPage'
import { AdminRefundRequestDetailPage } from './pages/AdminRefundRequestDetailPage'
import { AdminRefundsPage } from './pages/AdminRefundsPage'
import { CustomerHomePage } from './pages/CustomerHomePage'
import { CustomerOrderDetailPage } from './pages/CustomerOrderDetailPage'
import { CustomerOrdersPage } from './pages/CustomerOrdersPage'
import { CustomerRefundRequestDetailPage } from './pages/CustomerRefundRequestDetailPage'
import { CustomerRefundRequestsPage } from './pages/CustomerRefundRequestsPage'
import { NotFoundPage } from './pages/ForbiddenPage'
import { LoginPage } from './pages/LoginPage'

const CUSTOMER_NAV = [
  { to: '/customer', label: '我的售后', end: true },
  { to: '/customer/orders', label: '我的订单' },
  { to: '/customer/refund-requests', label: '我的申请' },
]

const ADMIN_NAV = [
  { to: '/admin', label: '概览', end: true },
  { to: '/admin/orders', label: '订单' },
  { to: '/admin/refunds', label: '退款审批' },
  { to: '/admin/refund-approvals', label: '审批记录' },
  { to: '/admin/refund-records', label: '退款流水' },
]

/** 根路径按登录态与角色分流 —— 三种去处只在这里判断一次。 */
function RootRedirect() {
  const { user, initializing } = useAuth()
  // 身份还没确认完就跳，会把已登录的人送进登录页，所以先等 `/me` 回来。
  if (initializing) return <AuthLoading />
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />

      {/* 客户区：必须是 customer 角色。
          注意页面路径与接口路径是两套：这里是页面（React Router 管），
          数据接口统一在 /api/**（后端管）。 */}
      <Route
        path="/customer"
        element={
          <RequireRole role="customer">
            <AppLayout nav={CUSTOMER_NAV} />
          </RequireRole>
        }
      >
        <Route index element={<CustomerHomePage />} />
        <Route path="orders" element={<CustomerOrdersPage />} />
        <Route path="orders/:orderNo" element={<CustomerOrderDetailPage />} />
        <Route path="refund-requests" element={<CustomerRefundRequestsPage />} />
        <Route path="refund-requests/:requestKey" element={<CustomerRefundRequestDetailPage />} />
      </Route>

      {/* 管理区：必须是 admin 角色 */}
      <Route
        path="/admin"
        element={
          <RequireRole role="admin">
            <AppLayout nav={ADMIN_NAV} />
          </RequireRole>
        }
      >
        <Route index element={<AdminHomePage />} />
        <Route path="orders" element={<AdminOrdersPage />} />
        <Route path="orders/:orderNo" element={<AdminOrderDetailPage />} />
        <Route path="refunds" element={<AdminRefundsPage />} />
        <Route path="refunds/:requestKey" element={<AdminRefundRequestDetailPage />} />
        <Route path="refund-approvals" element={<AdminRefundApprovalsPage />} />
        <Route path="refund-records" element={<AdminRefundRecordsPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
