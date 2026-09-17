<script setup lang="ts">
import { fetchMyRefundRequests } from '../api/customer'
import ResourceListPage from '../components/ResourceListPage.vue'
</script>

<template>
  <!-- 我的退款申请 —— GET /customer/refund-requests -->
  <ResourceListPage
    title="我的退款申请"
    :fetcher="fetchMyRefundRequests"
    detail-key="request_key"
    :detail-to="(requestKey: string) => `/customer/refund-requests/${requestKey}`"
  >
    来自 <code>GET /api/customer/refund-requests?offset=&amp;limit=</code>
    。点「查看」看单条申请的进度。

    <template #empty-hint>
      后端 refund_requests 表还没有数据 —— 提交入口（POST /customer/refund-requests）也还没实现。
    </template>
  </ResourceListPage>
</template>
