<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { fetchMyOrder, fetchRefundEligibility } from '../../api/customer'
import { useApi } from '../../composables/useApi'
import OrderItems from '../../components/orders/OrderItems.vue'
import OrderTimeline from '../../components/orders/OrderTimeline.vue'
import RefundApplyForm from '../../components/refunds/RefundApplyForm.vue'
import RefundEligibilityPanel from '../../components/refunds/RefundEligibilityPanel.vue'
import ResourceDetailPage from '../../components/common/ResourceDetailPage.vue'

/**
 * 时间线字段：从默认的键值表里摘出去，交给 `OrderTimeline` 单独排版。
 * 不摘的话，页面上会直接显示 `2026-09-04T10:17:01.042Z` 这种原文。
 */
const TIMELINE_KEYS = ['created_at', 'paid_at', 'shipped_at', 'delivered_at']

/** `items` 是数组，摊进键值表只会变成一坨 [object Object]，同样交给子组件渲染成表格。 */
const OMIT_KEYS = ['items', ...TIMELINE_KEYS]

/** 订单详情 —— GET /customer/orders/{order_no} + 退款资格子接口 */
const route = useRoute()
const orderNo = String(route.params.orderNo ?? '')

/**
 * 退款资格**只请求一次**，由这个页面拿着，再分给下面的面板和表单。
 *
 * 为什么不各自请求一次：两个组件各发一次就会出现"面板说能退、按钮是灰的"，
 * 更糟的是两次请求之间订单状态可能已经变了（比如管理员刚好批了退款）。
 * 一份结果、两个消费者，界面就不可能自相矛盾。
 */
const {
  state: eligibilityState,
  data: eligibilityData,
  error: eligibilityError,
  reload: reloadEligibility,
} = useApi(() => fetchRefundEligibility(orderNo))

/** 不能提交时按钮旁边显示的原因。 */
const blockReason = computed(() => {
  if (!eligibilityData.value) return '正在判定退款资格…'
  if (eligibilityData.value.eligible) return ''
  if (eligibilityData.value.existing_request_key) {
    return '该订单已有一条进行中的申请，请直接查看它的进度。'
  }
  return eligibilityData.value.reason_text
})
</script>

<template>
  <ResourceDetailPage
    :title="`订单 ${orderNo}`"
    :fetcher="() => fetchMyOrder(orderNo)"
    back-to="/customer/orders"
    back-label="返回我的订单"
    :omit-keys="OMIT_KEYS"
  >
    来自 <code>GET /api/customer/orders/{{ orderNo }}</code>，含商品明细。
    不是我的订单会返回 404「订单不存在」，跟订单根本不存在时的响应完全一样。

    <!-- 跟管理侧详情同一个骨架：时间线 + 商品明细，都靠作用域插槽拿到主数据 -->
    <template #data-extra="{ data }">
      <OrderTimeline :data="data" />
      <OrderItems :data="data" />
    </template>

    <template #extra>
      <RefundEligibilityPanel
        :state="eligibilityState"
        :data="eligibilityData"
        :error="eligibilityError"
        @retry="reloadEligibility"
      />
    </template>

    <template #actions>
      <RefundApplyForm
        :order-no="orderNo"
        :eligible="eligibilityData?.eligible === true"
        :amount-cents="eligibilityData?.amount_cents ?? 0"
        :block-reason="blockReason"
      />
    </template>
  </ResourceDetailPage>
</template>
