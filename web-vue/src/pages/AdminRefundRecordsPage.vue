<script setup lang="ts">
import { fetchRefundRecords } from '../api/admin'
import ResourceListPage from '../components/ResourceListPage.vue'
import StubNotice from '../components/StubNotice.vue'
</script>

<template>
  <!-- 退款执行流水 —— GET /admin/refund-records -->
  <ResourceListPage
    title="退款流水"
    :fetcher="fetchRefundRecords"
  >
    来自 <code>GET /api/admin/refund-records?offset=&amp;limit=</code>
    ：批准之后真正打款给支付渠道的执行记录。

    <template #notice>
      <StubNotice>
        这里关心的是<strong>执行结果</strong>而不是审批意见：<code>attempt_count</code>
        （重试了几次）、<code>last_error</code>（失败原因）、<code>succeeded_at</code>
        （成功时间）。退款执行还是空实现。
      </StubNotice>
    </template>

    <template #empty-hint>还没有退款执行记录。</template>
  </ResourceListPage>
</template>
