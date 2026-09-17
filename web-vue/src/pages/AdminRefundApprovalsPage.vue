<script setup lang="ts">
import { fetchRefundApprovals } from '../api/admin'
import ResourceListPage from '../components/ResourceListPage.vue'
import StubNotice from '../components/StubNotice.vue'
</script>

<template>
  <!-- 审批记录（审计用）—— GET /admin/refund-approvals -->
  <ResourceListPage
    title="审批记录"
    :fetcher="fetchRefundApprovals"
  >
    来自 <code>GET /api/admin/refund-approvals?offset=&amp;limit=</code>
    ：每一次批准 / 拒绝留下的凭据。

    <template #notice>
      <StubNotice>
        这张表<strong>一个申请只有一行</strong>（<code>refund_request_id</code> 是
        <code>unique</code>），所以只有被决策过的申请才会出现在这里 ——
        待办申请请去「退款审批」页看。
      </StubNotice>
    </template>

    <template #empty-hint>还没有任何审批发生过 —— 待办列表那边也没有数据。</template>
  </ResourceListPage>
</template>
