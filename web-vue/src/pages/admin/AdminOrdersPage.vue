<script setup lang="ts">
import { fetchOrders } from '../../api/admin'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import type { Column } from '../../components/common/table'
import { formatCents, formatDateTime } from '../../components/common/value'
import { FULFILLMENT_STATUS_LABELS, PAYMENT_STATUS_LABELS, labelOf } from '../../labels'

/**
 * 列表列：**显式声明**，不用自动推导。
 * 推导出来的列会跟着后端字段走 —— 哪天接口多返回一个 `user_id`，
 * 表头就自己多一列，界面什么时候变的都没人知道。
 *
 * 注意 `render` 返回的是**字符串**（Vue 的列渲染不像 React 那样能返回 JSX）。
 */
const COLUMNS: Column[] = [
  { key: 'order_no', label: '订单号' },
  { key: 'username', label: '归属客户' },
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
  <ResourceListPage
    title="订单"
    :fetcher="fetchOrders"
    :columns="COLUMNS"
    detail-key="order_no"
    :detail-to="(orderNo: string) => `/admin/orders/${orderNo}`"
  >
    全部客户的订单。点「查看」进入详情核对退款依据。

    <template #empty-hint>
      暂时没有订单记录。
    </template>
  </ResourceListPage>
</template>
