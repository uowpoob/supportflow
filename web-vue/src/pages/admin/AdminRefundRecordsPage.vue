<script setup lang="ts">
import { fetchRefundRecords } from '../../api/admin'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import StubNotice from '../../components/common/StubNotice.vue'
import type { Column } from '../../components/common/table'
import { formatCents, formatDateTime } from '../../components/common/value'
import {
  refundExecutionCellClass,
  refundExecutionText,
} from '../../components/refunds/refundTag'

/**
 * 显式列定义。
 *
 * 这张表**不能**靠自动推列 —— 后端字段是面向"执行"的
 * （`attempt_count` / `last_error` / `succeeded_at`），
 * 自动推出来的列头是英文下划线字段名，且金额会原样显示成分。
 */
const COLUMNS: Column[] = [
  {
    key: 'order_no',
    label: '订单号',
    render: (row) => String(row.order_no ?? ''),
  },
  {
    key: 'request_key',
    label: '申请编号',
    render: (row) => String(row.request_key ?? '').slice(0, 8),
  },
  { key: 'refund_no', label: '退款单号' },
  {
    key: 'amount_cents',
    label: '退款金额',
    render: (row) => formatCents(row.amount_cents),
  },
  {
    key: 'status',
    label: '执行结果',
    render: (row) => refundExecutionText(row),
    cellClass: (row) => refundExecutionCellClass(row),
  },
  { key: 'attempt_count', label: '尝试次数' },
  {
    key: 'succeeded_at',
    label: '成功时间',
    render: (row) => formatDateTime(row.succeeded_at),
  },
  {
    key: 'last_error',
    label: '失败原因',
    render: (row) => String(row.last_error ?? ''),
  },
]
</script>

<template>
  <ResourceListPage
    title="退款流水"
    :fetcher="fetchRefundRecords"
    :columns="COLUMNS"
  >
    审批通过后实际打款的执行记录，包含成功时间和失败原因。

    <template #notice>
      <StubNotice>
        这里记录的是退款的执行结果。有申请不等于退过款 ——
        只有审批通过的申请才会留下记录，被拒绝的不会出现在这里。
        <br />
        当前演示环境的退款是模拟执行的，结果均为成功。
      </StubNotice>
    </template>

    <template #empty-hint>还没有退款执行记录。</template>
  </ResourceListPage>
</template>
