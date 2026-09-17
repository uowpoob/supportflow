<script setup lang="ts">
import { fetchRefundApprovals } from '../api/admin'
import ResourceListPage from '../components/ResourceListPage.vue'
import StubNotice from '../components/StubNotice.vue'
import type { Column } from '../components/table'
import { formatDateTime } from '../components/value'
import { APPROVAL_DECISION_LABELS, labelOf } from '../labels'

const COLUMNS: Column[] = [
  { key: 'order_no', label: '订单号' },
  { key: 'decision', label: '决策', render: (row) => labelOf(APPROVAL_DECISION_LABELS, row.decision) },
  { key: 'admin_username', label: '审批人' },
  { key: 'comment', label: '审批意见' },
  { key: 'decided_at', label: '审批时间', render: (row) => formatDateTime(row.decided_at) },
  {
    key: 'request_key',
    label: '申请编号',
    render: (row) => String(row.request_key ?? '').slice(0, 8),
  },
]
</script>

<template>
  <!-- 审批记录（审计用）—— GET /admin/refund-approvals -->
  <ResourceListPage
    title="审批记录"
    :fetcher="fetchRefundApprovals"
    :columns="COLUMNS"
  >
    来自 <code>GET /api/admin/refund-approvals?offset=&amp;limit=</code>
    ：每一次批准 / 拒绝留下的凭据，包含"是谁批的"。

    <template #notice>
      <StubNotice>
        这张表<strong>一个申请只有一行</strong>（<code>refund_request_id</code> 是
        <code>unique</code>），所以只有被决策过的申请才会出现在这里 ——
        待办申请请去「退款审批」页看。
      </StubNotice>
    </template>

    <template #empty-hint>还没有任何审批发生过。</template>
  </ResourceListPage>
</template>
