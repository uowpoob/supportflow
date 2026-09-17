<script setup lang="ts">
import { useRoute } from 'vue-router'

import { fetchMyRefundRequest } from '../api/customer'
import ResourceDetailPage from '../components/ResourceDetailPage.vue'
import StubNotice from '../components/StubNotice.vue'

/** 退款申请进度 —— GET /customer/refund-requests/{request_key} */
const route = useRoute()
const requestKey = String(route.params.requestKey ?? '')
</script>

<template>
  <ResourceDetailPage
    :title="`退款申请 ${requestKey}`"
    :fetcher="() => fetchMyRefundRequest(requestKey)"
    back-to="/customer/refund-requests"
    back-label="返回我的申请"
  >
    来自 <code>GET /api/customer/refund-requests/{{ requestKey }}</code>
    ：状态、审批意见、退款结果。

    <template #notice>
      <StubNotice>
        后端尚未实现。按项目约定，<strong>「不是你的申请」和「申请不存在」必须返回完全相同的结果</strong>
        ，否则一区分就等于告诉别人「这个申请是存在的」。
      </StubNotice>
    </template>
  </ResourceDetailPage>
</template>
