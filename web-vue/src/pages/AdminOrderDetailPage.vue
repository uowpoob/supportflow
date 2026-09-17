<script setup lang="ts">
import { useRoute } from 'vue-router'

import { fetchOrder } from '../api/admin'
import OrderItems from '../components/OrderItems.vue'
import OrderTimeline from '../components/OrderTimeline.vue'
import ResourceDetailPage from '../components/ResourceDetailPage.vue'

/** 时间线字段：从主键值表里摘出去，交给 `OrderTimeline` 单独排版。 */
const TIMELINE_KEYS = ['created_at', 'paid_at', 'shipped_at', 'delivered_at']

/** `items` 是个数组，摊在键值表里没法看，也交给子组件渲染成表格。 */
const OMIT_KEYS = ['items', ...TIMELINE_KEYS]

/** 订单详情（管理侧）—— GET /admin/orders/{order_no}，审批时核对退款依据用 */
const route = useRoute()
const orderNo = String(route.params.orderNo ?? '')
</script>

<template>
  <ResourceDetailPage
    :title="`订单 ${orderNo}`"
    :fetcher="() => fetchOrder(orderNo)"
    back-to="/admin/orders"
    back-label="返回订单列表"
    :omit-keys="OMIT_KEYS"
  >
    来自 <code>GET /api/admin/orders/{{ orderNo }}</code>，含商品明细与实付金额。

    <!-- React 版这里是 `renderExtra(data)` 函数；Vue 用作用域插槽，
         `data` 从槽的 props 里拿。 -->
    <template #data-extra="{ data }">
      <OrderTimeline :data="data" />
      <OrderItems :data="data" />
    </template>
  </ResourceDetailPage>
</template>
