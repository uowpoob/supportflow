<script setup lang="ts">
import { computed, toRef } from 'vue'
import { RouterLink } from 'vue-router'

import type { AsyncState } from '../composables/useApi'
import type { RefundEligibility } from '../types'
import ErrorAlert from './ErrorAlert.vue'
import LoadingLine from './LoadingLine.vue'
import { formatCents, formatDateTime } from './value'

/**
 * 退款资格面板 —— **纯展示组件**，自己不发请求。
 *
 * 为什么把请求留在页面里？因为"能不能退"要同时决定两件事：
 * 这块面板显示什么，以及旁边的提交按钮能不能点。
 * 让两个组件各发一次请求，就会出现"面板说能退、按钮是灰的"这种自相矛盾的界面；
 * 更糟的是两次请求之间状态可能已经变了。
 * 所以资格只请求一次，由页面拿在手里，往下分发给面板和表单。
 */
const props = defineProps<{
  state: AsyncState
  data: RefundEligibility | null
  error: string
}>()

defineEmits<{ retry: [] }>()

const eligibility = toRef(props, 'data')

/** 申请截止时间：只有真正有签收时间才有值（未签收的订单算不出窗口）。 */
const deadline = computed(() => eligibility.value?.window_ends_at ?? null)
</script>

<template>
  <section class="section">
    <h3 class="section__title">退款资格</h3>

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="$emit('retry')" />

    <template v-else-if="state === 'done' && eligibility">
      <div class="verdict">
        <div class="verdict__head">
          <span class="tag" :class="eligibility.eligible ? 'tag--ok' : 'tag--danger'">
            {{ eligibility.eligible ? '可以申请' : '不能申请' }}
          </span>
          <span>{{ eligibility.reason_text }}</span>
        </div>

        <p v-if="eligibility.eligible" class="verdict__detail">
          可退金额 {{ formatCents(eligibility.amount_cents) }}（订单实付原路全额退）
          <template v-if="deadline">
            ，申请截止 {{ formatDateTime(deadline) }}
          </template>
        </p>

        <p v-else class="verdict__detail">
          <template v-if="deadline">
            该订单的退款窗口是签收后 14 天内（截止 {{ formatDateTime(deadline) }}）。
          </template>
          判定依据：<code>{{ eligibility.reason_code }}</code>
        </p>

        <p v-if="eligibility.existing_request_key" class="verdict__detail">
          已有进行中的申请：
          <RouterLink
            class="link"
            :to="`/customer/refund-requests/${eligibility.existing_request_key}`"
          >
            查看进度
          </RouterLink>
        </p>
      </div>
    </template>
  </section>
</template>
