import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth/AuthContext'
import { RequireRole } from './auth/guards'
import { homePathFor } from './auth/paths'
import { AppLayout } from './layouts/AppLayout'
import { AdminHomePage } from './pages/AdminHomePage'
import { AdminOrdersPage } from './pages/AdminOrdersPage'
import { AdminRefundsPage } from './pages/AdminRefundsPage'
import { CustomerHomePage } from './pages/CustomerHomePage'
import { NotFoundPage } from './pages/ForbiddenPage'
import { LoginPage } from './pages/LoginPage'

const CUSTOMER_NAV = [{ to: '/customer', label: '我的售后', end: true }]

const ADMIN_NAV = [
  { to: '/admin', label: '概览', end: true },
  { to: '/admin/orders', label: '订单' },
  { to: '/admin/refunds', label: '退款审批' },
]

/** 根路径按登录态与角色分流 —— 三种去处只在这里判断一次。 */
function RootRedirect() {
  const { user } = useAuth()
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />

      {/* 客户区：必须是 customer 角色 */}
      <Route
        path="/customer"
        element={
          <RequireRole role="customer">
            <AppLayout nav={CUSTOMER_NAV} />
          </RequireRole>
        }
      >
        <Route index element={<CustomerHomePage />} />
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
        <Route path="refunds" element={<AdminRefundsPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
