<script setup lang="ts">
import { fetchMyRefundRequests } from '../../api/customer'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import { refundStatusCellClass, refundStatusText } from '../../components/refunds/refundTag'
import type { Column } from '../../components/common/table'
import { formatCents, formatDateTime } from '../../components/common/value'

/**
 * 列显式写出来，不再靠"取数据里出现的所有键"自动生成。
 *
 * 退款接口的字段已经定稿，自动生成的列会按 JSON 的键顺序排，
 * 出现 `request_key` 这种 36 位 UUID 挤满一屏 —— 显式写还能顺手做金额和时间的格式化。
 * `request_key` 只取前 8 位当标识，完整编号在详情页里。
 */
const COLUMNS: Column[] = [
  { key: 'order_no', label: '订单号' },
  { key: 'amount_cents', label: '退款金额', render: (row) => formatCents(row.amount_cents) },
  {
    key: 'status',
    label: '状态',
    render: refundStatusText,
    cellClass: refundStatusCellClass,
  },
  { key: 'created_at', label: '提交时间', render: (row) => formatDateTime(row.created_at) },
  {
    key: 'request_key',
    label: '申请编号',
    render: (row) => String(row.request_key ?? '').slice(0, 8),
  },
]
</script>

<template>
  <ResourceListPage
    title="我的退款申请"
    :fetcher="fetchMyRefundRequests"
    :columns="COLUMNS"
    detail-key="request_key"
    :detail-to="(requestKey: string) => `/customer/refund-requests/${requestKey}`"
  >
    你提交过的退款申请。点「查看」可以看到处理进度、审批意见和退款结果。

    <template #empty-hint>
      还没有提交过退款申请。到「我的订单」里打开一单已签收的订单，就能看到申请入口。
    </template>
  </ResourceListPage>
</template>
