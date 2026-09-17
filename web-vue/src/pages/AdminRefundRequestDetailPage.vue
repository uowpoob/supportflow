<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { decideRefundRequest, fetchRefundRequest } from '../api/admin'
import { ApiError } from '../api/client'
import { useApi } from '../composables/useApi'
import ErrorAlert from '../components/ErrorAlert.vue'
import LoadingLine from '../components/LoadingLine.vue'
import RefundRequestSections from '../components/RefundRequestSections.vue'
import StubNotice from '../components/StubNotice.vue'
import type { ApprovalDecision } from '../types'

/** 退款申请详情 + 审批 —— GET / POST /admin/refund-requests/{request_key} */
const route = useRoute()
const requestKey = String(route.params.requestKey ?? '')

const { state, data, error, reload } = useApi(() => fetchRefundRequest(requestKey))

const comment = ref('')
const submitting = ref(false)
const actionError = ref('')

/**
 * 只有 `pending` 的申请能决策。
 *
 * 界面这样禁按钮只是体验，**后端也会拦**：改判已决的申请返回 409。
 * 别把这里的判断当安全边界 —— 直接 curl 就绕过去了。
 */
const decidable = computed(() => data.value?.status === 'pending')

async function decide(decision: ApprovalDecision): Promise<void> {
  if (submitting.value) return
  actionError.value = ''
  submitting.value = true
  try {
    await decideRefundRequest(requestKey, {
      decision,
      // 空意见存成 null 而不是空字符串，避免库里出现两种"没写"。
      comment: comment.value.trim() || null,
    })
    comment.value = ''
    // 不做本地拼接，直接把整页重读一遍 —— 审批会同时改申请状态、写流水、
    // 改订单支付状态，本地拼很容易漏掉其中一处，读回来才是唯一可信的来源。
    reload()
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : '审批失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <p class="crumbs">
        <RouterLink class="link" to="/admin/refunds">← 返回待办列表</RouterLink>
      </p>
      <h2 class="page-head__title">退款申请审批</h2>
      <p class="page-head__desc">
        来自 <code>GET /api/admin/refund-requests/{{ requestKey }}</code>
        ：客户填写的原因原文、订单依据、已有审批与退款流水。
      </p>
    </header>

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="reload" />

    <template v-else-if="state === 'done' && data">
      <section class="section">
        <h3 class="section__title">审批</h3>

        <template v-if="decidable">
          <StubNotice>
            <strong>批准会立刻执行模拟退款</strong>：在同一个数据库事务里改申请状态、
            写退款流水、把订单标成已退款。批准前会再核对一次归属、支付状态和实付金额，
            对不上就拒绝执行并给出原因。
            审批人取自登录态，请求体里没有 <code>admin_id</code>，伪造不了。
          </StubNotice>

          <div class="field">
            <label class="field__label" for="refund-comment">审批意见（可选，会记录在案）</label>
            <textarea
              id="refund-comment"
              v-model="comment"
              class="field__input field__textarea"
              rows="2"
              maxlength="1000"
              :disabled="submitting"
              placeholder="例如：已核对签收时间与实付金额，同意退款"
            />
          </div>

          <p v-if="actionError" class="alert alert--error">{{ actionError }}</p>

          <div class="page-actions">
            <button
              type="button"
              class="btn btn--primary"
              :disabled="submitting"
              @click="decide('approved')"
            >
              {{ submitting ? '处理中…' : '批准并执行退款' }}
            </button>
            <button
              type="button"
              class="btn btn--ghost"
              :disabled="submitting"
              @click="decide('rejected')"
            >
              拒绝
            </button>
          </div>
        </template>

        <p v-else class="muted">
          这条申请已经是「{{ data.status }}」，审批按钮已禁用 ——
          已生效的决策不能被覆盖。重复提交<strong>相同</strong>的决策是幂等的（返回当前结果），
          用<strong>不同</strong>的决策去打会返回 409。
        </p>
      </section>

      <RefundRequestSections :data="data" />
    </template>
  </div>
</template>
