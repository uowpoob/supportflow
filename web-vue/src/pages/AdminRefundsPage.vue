<script setup lang="ts">
import { fetchRefundRequests } from '../api/admin'
import ResourceListPage from '../components/ResourceListPage.vue'
import StubNotice from '../components/StubNotice.vue'
</script>

<template>
  <!-- 待办队列：待审批的退款申请 —— GET /admin/refund-requests -->
  <ResourceListPage
    title="待办：退款审批"
    :fetcher="fetchRefundRequests"
    detail-key="request_key"
    :detail-to="(requestKey: string) => `/admin/refunds/${requestKey}`"
    detail-label="审批"
  >
    来自 <code>GET /api/admin/refund-requests?offset=&amp;limit=</code> ——
    <code>refund_requests</code> 里 <code>status='pending'</code> 的申请。

    <template #notice>
      <StubNotice>
        这里查的是<strong>待办申请</strong>（<code>refund_requests</code>），不是审批记录（
        <code>refund_approvals</code>）。批准之前后者根本没有对应行 ——
        拿它当待办列表用会永远查出空数组。
      </StubNotice>
    </template>

    <template #empty-hint>
      refund_requests 表还没有数据 —— 客户的提交入口（POST /customer/refund-requests）也还没实现。
    </template>
  </ResourceListPage>
</template>
