<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { decideRefundRequest, fetchRefundRequest, resumeRefundApproval } from '../../api/admin'
import { ApiError } from '../../api/client'
import { useApi } from '../../composables/useApi'
import ErrorAlert from '../../components/common/ErrorAlert.vue'
import LoadingLine from '../../components/common/LoadingLine.vue'
import RefundRequestSections from '../../components/refunds/RefundRequestSections.vue'
import StubNotice from '../../components/common/StubNotice.vue'
import { REFUND_STATUS_LABELS, labelOf } from '../../labels'
import type { ApprovalDecision } from '../../types'

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

const resuming = ref(false)
const resumeNotice = ref('')

/**
 * 手动重试"把客户的会话推一步"。
 *
 * 审批接口提交决策后会自己尝试恢复，正常情况下这里不需要点。
 * 只有那一步失败（后端日志里是 `审批已提交，但会话恢复失败`）时才有用 ——
 * 所以它不该做成这一步的主路径，界面上也只放在已决策之后。
 */
async function resumeConversation(): Promise<void> {
  if (resuming.value) return
  resuming.value = true
  actionError.value = ''
  resumeNotice.value = ''
  try {
    await resumeRefundApproval(requestKey)
    resumeNotice.value = '已请求同步客户对话。若客户那边没有立刻更新，让他刷新一下会话即可。'
  } catch (err) {
    actionError.value = err instanceof ApiError ? err.message : '恢复客户会话失败'
  } finally {
    resuming.value = false
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
        客户填写的原因、订单依据，以及已有的审批意见与退款记录。
      </p>
    </header>

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="reload" />

    <template v-else-if="state === 'done' && data">
      <section class="section">
        <h3 class="section__title">审批</h3>

        <template v-if="decidable">
          <StubNotice>
            批准后会立即执行退款：更新申请状态、记录退款流水，并把订单标记为已退款。
            批准前会再核对一次订单归属、支付状态和实付金额，对不上会拒绝执行并说明原因。
            如果这条申请是客户在对话里提交的，审批结果会同步回那条对话，客户能看到。
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
          这条申请已经是「{{ labelOf(REFUND_STATUS_LABELS, data.status) }}」，不能再改判了。
          重复提交相同的决定不会有任何影响，改成相反的决定会被拒绝。
        </p>

        <!-- 审批已落库之后才可能出现这条分支：客户那条会话没被推起来时手动重试。 -->
        <template v-if="!decidable">
          <p v-if="actionError" class="alert alert--error">{{ actionError }}</p>
          <p v-if="resumeNotice" class="alert alert--info">{{ resumeNotice }}</p>
          <div class="page-actions">
            <button
              type="button"
              class="btn btn--ghost"
              :disabled="resuming"
              @click="resumeConversation"
            >
              {{ resuming ? '恢复中…' : '重试恢复客户会话' }}
            </button>
          </div>
          <p class="muted">
            如果客户的对话没有自动更新到审批结果，点上面的按钮再同步一次，重复点击不会重复退款。
          </p>
        </template>
      </section>

      <RefundRequestSections :data="data" />
    </template>
  </div>
</template>
