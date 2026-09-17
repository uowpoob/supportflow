<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { submitRefundRequest } from '../api/customer'
import { ApiError } from '../api/client'
import { formatCents } from './value'

/**
 * 提交退款申请的表单。
 *
 * 三件事值得注意：
 *
 * 1. **请求体只有订单号和原因。** 金额、用户、状态都不传 —— 金额由后端从订单实付取，
 *    身份由 Cookie 决定，新申请一律 pending。前端少传一个字段就少一条能被伪造的路径。
 * 2. **提交成功后跳到详情页**，而不是停在原地显示"成功"。用户真正想知道的是
 *    "我的申请现在是什么状态、多久能出结果"，详情页正好回答这个。
 * 3. **按钮是否可点由外面传来的 `eligible` 决定**，不在这里自己再判一次 ——
 *    资格只请求一次，来源单一。
 */
const props = withDefaults(
  defineProps<{
    orderNo: string
    eligible: boolean
    amountCents: number
    /** 不能提交时显示的原因（比如"已有进行中的申请"） */
    blockReason?: string
  }>(),
  { blockReason: '' },
)

const router = useRouter()
const reason = ref('')
const submitting = ref(false)
const error = ref('')

const amountText = computed(() =>
  props.amountCents > 0 ? formatCents(props.amountCents) : '订单实付金额',
)

async function submit(): Promise<void> {
  if (submitting.value) return
  error.value = ''

  const text = reason.value.trim()
  if (!text) {
    // 后端也会拦（422），但让用户等一个来回没必要。
    error.value = '请填写退款原因'
    return
  }

  submitting.value = true
  try {
    const created = await submitRefundRequest({ order_no: props.orderNo, reason: text })
    // 幂等：如果这单已经申请过，后端返回的是既有那条，跳过去看它就行。
    await router.push(`/customer/refund-requests/${created.request_key}`)
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : '提交失败，请稍后重试'
    if (err instanceof ApiError && err.details.length > 0) {
      error.value = `${error.value}（${err.details.join('；')}）`
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="section">
    <h3 class="section__title">提交退款申请</h3>

    <template v-if="eligible">
      <div class="field">
        <label class="field__label" :for="`refund-reason-${orderNo}`">
          退款原因（会原样保存，请写清楚问题）
        </label>
        <textarea
          :id="`refund-reason-${orderNo}`"
          v-model="reason"
          class="field__input field__textarea"
          rows="3"
          maxlength="1000"
          placeholder="例如：左耳无声，不是物流损坏"
          :disabled="submitting"
        />
      </div>

      <p v-if="error" class="alert alert--error">{{ error }}</p>

      <div class="page-actions">
        <button type="button" class="btn btn--primary" :disabled="submitting" @click="submit">
          {{ submitting ? '提交中…' : `提交全额退款申请（${amountText}）` }}
        </button>
        <span class="muted">
          金额取订单实付，不可修改；提交后进入待审批，管理员批准才真正退款。
        </span>
      </div>
    </template>

    <template v-else>
      <p class="muted">{{ blockReason || '当前不满足退款条件，按钮已禁用。' }}</p>
      <div class="page-actions">
        <button type="button" class="btn btn--primary" disabled>提交退款申请</button>
      </div>
    </template>
  </section>
</template>
