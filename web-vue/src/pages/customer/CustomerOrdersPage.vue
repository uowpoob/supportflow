<script setup lang="ts">
import { fetchMyOrders } from '../../api/customer'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import type { Column } from '../../components/common/table'
import { formatCents, formatDateTime } from '../../components/common/value'
import {
  fulfillmentStatusCellClass,
  fulfillmentStatusText,
  paymentStatusCellClass,
  paymentStatusText,
} from '../../components/orders/orderTag'

/**
 * 列显式声明。管理侧的列多一个「归属客户」—— 这里恒等于自己，没意义。
 * 列渲染返回**字符串**（Vue 的列不像 React 那样能返回 JSX），
 * 金额换元、枚举换中文都在 `render` 里做，后端只出原始值。
 * 状态列的配色归 `cellClass` 管（文案归 `render`），和退款列表同一个套路。
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
    render: paymentStatusText,
    cellClass: paymentStatusCellClass,
  },
  {
    key: 'fulfillment_status',
    label: '履约状态',
    render: fulfillmentStatusText,
    cellClass: fulfillmentStatusCellClass,
  },
  {
    key: 'created_at',
    label: '下单时间',
    render: (row) => formatDateTime(row.created_at),
  },
]
</script>

<template>
  <ResourceListPage
    title="我的订单"
    :fetcher="fetchMyOrders"
    :columns="COLUMNS"
    detail-key="order_no"
    :detail-to="(orderNo: string) => `/customer/orders/${orderNo}`"
  >
    你名下的全部订单。点「查看」进入订单详情，核对商品明细与实付金额。

    <template #empty-hint>
      暂时还没有订单。
    </template>
  </ResourceListPage>
</template>
