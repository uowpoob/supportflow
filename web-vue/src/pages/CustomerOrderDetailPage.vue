<script setup lang="ts">
import { useRoute } from 'vue-router'

import { fetchMyOrder, fetchRefundEligibility } from '../api/customer'
import AsyncSection from '../components/AsyncSection.vue'
import OrderItems from '../components/OrderItems.vue'
import OrderTimeline from '../components/OrderTimeline.vue'
import ResourceDetailPage from '../components/ResourceDetailPage.vue'
import StubNotice from '../components/StubNotice.vue'

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

    <template #actions>
      <section class="section">
        <h3 class="section__title">提交退款申请</h3>
        <StubNotice>
          提交入口是 <code>POST /api/customer/refund-requests</code>
          ，后端尚未实现、请求体（退款原因、金额）也还没定，所以按钮先禁用。
        </StubNotice>
        <div class="page-actions">
          <button type="button" class="btn btn--primary" disabled>提交退款申请</button>
          <span class="muted">等 POST /customer/refund-requests 定稿后启用</span>
        </div>
      </section>
    </template>

    <template #extra>
      <AsyncSection title="退款资格" :fetcher="() => fetchRefundEligibility(orderNo)">
        <template #notice>
          <StubNotice>
            这是<strong>只读</strong>判定：只回答「能不能退、为什么不能」，不写库、不占额度，
            可以反复调用。真正的资格规则还没实现。
          </StubNotice>
        </template>
      </AsyncSection>
    </template>
  </ResourceDetailPage>
</template>
