<script setup lang="ts">
import { useRoute, RouterLink } from 'vue-router'

import { fetchMyRefundRequest } from '../api/customer'
import { useApi } from '../composables/useApi'
import ErrorAlert from '../components/ErrorAlert.vue'
import LoadingLine from '../components/LoadingLine.vue'
import RefundRequestSections from '../components/RefundRequestSections.vue'

/** 退款申请进度 —— GET /customer/refund-requests/{request_key} */
const route = useRoute()
const requestKey = String(route.params.requestKey ?? '')

const { state, data, error, reload } = useApi(() => fetchMyRefundRequest(requestKey))
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <p class="crumbs">
        <RouterLink class="link" to="/customer/refund-requests">← 返回我的申请</RouterLink>
      </p>
      <h2 class="page-head__title">退款申请详情</h2>
      <p class="page-head__desc">
        来自 <code>GET /api/customer/refund-requests/{{ requestKey }}</code>
        ：当前状态、客户填写的原因、管理员的审批意见、以及退款是否真的执行过。
        <strong>别人的申请和不存在，返回的都是同一个 404</strong> ——
        区分开就等于告诉别人"这个申请是存在的"。
      </p>
    </header>

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="reload" />
    <RefundRequestSections v-else-if="state === 'done' && data" :data="data" />
  </div>
</template>
