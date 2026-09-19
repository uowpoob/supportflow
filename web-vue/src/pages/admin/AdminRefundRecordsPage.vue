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
  <!-- 退款执行流水 —— GET /admin/refund-records -->
  <ResourceListPage
    title="退款流水"
    :fetcher="fetchRefundRecords"
    :columns="COLUMNS"
  >
    来自 <code>GET /api/admin/refund-records?offset=&amp;limit=</code>
    ：批准之后真正打款给支付渠道的执行记录。

    <template #notice>
      <StubNotice>
        这里关心的是<strong>执行结果</strong>而不是审批意见：<code>attempt_count</code>
        （重试了几次）、<code>last_error</code>（失败原因）、<code>succeeded_at</code>
        （成功时间）。
        <br />
        注意<strong>有申请 ≠ 退过款</strong>：只有"批准"才在这一页留下行，
        被拒绝的申请永远不会出现在这里。演示里的退款是<strong>模拟</strong>的
        （不真调支付渠道），所以每次都是 <code>succeeded</code>、<code>attempt_count</code> 恒为 1，
        <code>last_error</code> 永远为空 —— 这两列是为将来接真实渠道留的。
      </StubNotice>
    </template>

    <template #empty-hint>还没有退款执行记录。</template>
  </ResourceListPage>
</template>
