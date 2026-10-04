<script setup lang="ts">
import { fetchRefundApprovals } from '../../api/admin'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import StubNotice from '../../components/common/StubNotice.vue'
import type { Column } from '../../components/common/table'
import { formatDateTime } from '../../components/common/value'
import { APPROVAL_DECISION_LABELS, labelOf } from '../../labels'

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
  <ResourceListPage
    title="审批记录"
    :fetcher="fetchRefundApprovals"
    :columns="COLUMNS"
  >
    每一次批准或拒绝留下的记录，包含处理人和审批意见。

    <template #notice>
      <StubNotice>
        每条申请只有一条审批记录，所以只有被处理过的申请会出现在这里。
        待处理的申请请到「退款审批」查看。
      </StubNotice>
    </template>

    <template #empty-hint>还没有任何审批发生过。</template>
  </ResourceListPage>
</template>
