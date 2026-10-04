<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import {
  APPROVAL_DECISION_LABELS,
  FULFILLMENT_STATUS_LABELS,
  PAYMENT_STATUS_LABELS,
  REFUND_EXECUTION_STATUS_LABELS,
  labelOf,
} from '../../labels'
import type { AdminRefundRequestDetail, MyRefundRequestDetail } from '../../types'
import RefundStatusTag from './RefundStatusTag.vue'
import { formatCents, formatDateTime } from '../common/value'

/**
 * 退款申请详情的四块内容：申请信息 / 订单依据 / 审批结果 / 退款流水。
 *
 * 客户侧和管理侧共用这一个组件 —— 两边看到的是**同一份事实**，
 * 差别只有"是否显示归属"（用 `'username' in data` 判断）。
 * 不共用的话，两份界面迟早会给出不一致的呈现，而这对"退款"这种事是危险的。
 *
 * 为什么不用 `ResourceDetailPage` + `KeyValueList` 那套？
 * 那套是给"字段还没定稿"的接口用的：它把对象摊开显示，金额是 `29900`、时间是
 * `2026-09-06T10:17:01.042Z`。退款接口的字段已经定稿，就该显示成
 * `¥299.00` 和 `2026-09-06 18:17`，而不是让用户自己换算。
 */
const props = defineProps<{ data: MyRefundRequestDetail | AdminRefundRequestDetail }>()

/** 管理侧的响应多带归属字段，用它来判断要不要显示"申请人"。 */
const owner = computed(() => {
  const record = props.data as AdminRefundRequestDetail
  return 'username' in props.data ? record : null
})

const approval = computed(() => props.data.approval)
const record = computed(() => props.data.refund_record)
</script>

<template>
  <section class="section">
    <h3 class="section__title">申请信息</h3>
    <dl class="kv">
      <div class="kv__row">
        <dt class="kv__key">申请编号</dt>
        <dd class="kv__value"><code>{{ data.request_key }}</code></dd>
      </div>
      <div v-if="owner" class="kv__row">
        <dt class="kv__key">申请人</dt>
        <dd class="kv__value">{{ owner.username }}（id {{ owner.user_id }}）</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">订单号</dt>
        <dd class="kv__value">
          <RouterLink
            class="link"
            :to="owner ? `/admin/orders/${data.order_no}` : `/customer/orders/${data.order_no}`"
          >
            {{ data.order_no }}
          </RouterLink>
        </dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">退款金额</dt>
        <dd class="kv__value">{{ formatCents(data.amount_cents) }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">状态</dt>
        <dd class="kv__value">
          <RefundStatusTag :status="data.status" />
        </dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">提交时间</dt>
        <dd class="kv__value">{{ formatDateTime(data.created_at) }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">最后更新</dt>
        <dd class="kv__value">{{ formatDateTime(data.updated_at) }}</dd>
      </div>
    </dl>

    <h4 class="kv__key">申请原因</h4>
    <p class="codeblock">{{ data.reason_original }}</p>
  </section>

  <section class="section">
    <h3 class="section__title">订单依据</h3>
    <p class="muted">
      下面几项是判定这笔退款是否合规的依据。
    </p>
    <dl class="kv">
      <div class="kv__row">
        <dt class="kv__key">订单实付</dt>
        <dd class="kv__value">{{ formatCents(data.order.paid_amount_cents) }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">支付状态</dt>
        <dd class="kv__value">{{ labelOf(PAYMENT_STATUS_LABELS, data.order.payment_status) }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">履约状态</dt>
        <dd class="kv__value">
          {{ labelOf(FULFILLMENT_STATUS_LABELS, data.order.fulfillment_status) }}
        </dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">签收时间</dt>
        <dd class="kv__value">{{ formatDateTime(data.order.delivered_at) || '（无）' }}</dd>
      </div>
    </dl>
    <p v-if="data.amount_cents !== data.order.paid_amount_cents" class="alert alert--warn">
      申请金额（{{ formatCents(data.amount_cents) }}）与订单实付金额（{{
        formatCents(data.order.paid_amount_cents)
      }}）不一致。审批前会再次核对，对不上会拒绝执行。
    </p>
  </section>

  <section class="section">
    <h3 class="section__title">审批结果</h3>
    <p v-if="!approval" class="muted">
      还没有审批结果，这条申请正在等待处理。
    </p>
    <dl v-else class="kv">
      <div class="kv__row">
        <dt class="kv__key">决策</dt>
        <dd class="kv__value">
          <span class="tag" :class="approval.decision === 'approved' ? 'tag--ok' : 'tag--danger'">
            {{ labelOf(APPROVAL_DECISION_LABELS, approval.decision) }}
          </span>
        </dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">审批人</dt>
        <dd class="kv__value">{{ approval.admin_username ?? '（未知）' }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">审批时间</dt>
        <dd class="kv__value">{{ formatDateTime(approval.decided_at) }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">审批意见</dt>
        <dd class="kv__value">{{ approval.comment || '（未填写）' }}</dd>
      </div>
    </dl>
  </section>

  <section class="section">
    <h3 class="section__title">退款流水</h3>
    <p v-if="!record" class="muted">
      还没有退款记录。<strong>提交申请不等于退款成功</strong> ——
      只有审批通过并完成打款，才会有退款记录。
    </p>
    <dl v-else class="kv">
      <div class="kv__row">
        <dt class="kv__key">退款单号</dt>
        <dd class="kv__value"><code>{{ record.refund_no }}</code></dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">执行状态</dt>
        <dd class="kv__value">
          <span class="tag" :class="record.status === 'succeeded' ? 'tag--ok' : 'tag--warn'">
            {{ labelOf(REFUND_EXECUTION_STATUS_LABELS, record.status) }}
          </span>
        </dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">退款金额</dt>
        <dd class="kv__value">{{ formatCents(record.amount_cents) }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">执行次数</dt>
        <dd class="kv__value">{{ record.attempt_count }}</dd>
      </div>
      <div class="kv__row">
        <dt class="kv__key">完成时间</dt>
        <dd class="kv__value">{{ formatDateTime(record.succeeded_at) || '（未完成）' }}</dd>
      </div>
      <div v-if="record.last_error" class="kv__row">
        <dt class="kv__key">最后一次错误</dt>
        <dd class="kv__value">{{ record.last_error }}</dd>
      </div>
    </dl>
  </section>
</template>
