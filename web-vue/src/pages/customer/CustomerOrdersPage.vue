<script setup lang="ts">
import { fetchMyOrders } from '../../api/customer'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import type { Column } from '../../components/common/table'
import { formatCents, formatDateTime } from '../../components/common/value'
import { FULFILLMENT_STATUS_LABELS, PAYMENT_STATUS_LABELS, labelOf } from '../../labels'

/**
 * 列显式声明。管理侧的列多一个「归属客户」—— 这里恒等于自己，没意义。
 * 列渲染返回**字符串**（Vue 的列不像 React 那样能返回 JSX），
 * 金额换元、枚举换中文都在 `render` 里做，后端只出原始值。
 */
const COLUMNS: Column[] = [
  { key: 'order_no', label: '订单号' },
  {
    key: 'paid_amount_cents',
    label: '实付金额',
    render: (row) => formatCents(row.paid_amount_cents),
  },
  {
    key: 'payment_status',
    label: '支付状态',
    render: (row) => labelOf(PAYMENT_STATUS_LABELS, row.payment_status),
  },
  {
    key: 'fulfillment_status',
    label: '履约状态',
    render: (row) => labelOf(FULFILLMENT_STATUS_LABELS, row.fulfillment_status),
  },
  {
    key: 'created_at',
    label: '下单时间',
    render: (row) => formatDateTime(row.created_at),
  },
]
</script>

<template>
  <!-- 我的订单 —— GET /customer/orders -->
  <ResourceListPage
    title="我的订单"
    :fetcher="fetchMyOrders"
    :columns="COLUMNS"
    detail-key="order_no"
    :detail-to="(orderNo: string) => `/customer/orders/${orderNo}`"
  >
    来自 <code>GET /api/customer/orders?offset=&amp;limit=</code>
    ，只包含当前登录账号自己的订单（身份取自 Cookie，不是请求参数）。

    <template #empty-hint>
      这个账号名下还没有订单。演示数据用
      <code>python -m supportflow.db.seed_orders</code> 生成。
    </template>
  </ResourceListPage>
</template>
