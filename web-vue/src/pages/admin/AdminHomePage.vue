<script setup lang="ts">
import { RouterLink } from 'vue-router'

import AppIcon from '../../components/common/AppIcon.vue'
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <h2 class="page-head__title">管理后台</h2>
      <p class="page-head__desc">查看订单、处理退款审批、查审批记录与退款流水。</p>
    </header>

    <div class="card-grid">
      <RouterLink class="entry-card entry-card--blue" to="/admin/orders">
        <span class="entry-card__icon"><AppIcon name="box" :size="20" /></span>
        <span class="entry-card__title">订单</span>
        <span class="entry-card__desc">查看全部订单，进详情核对退款依据</span>
      </RouterLink>

      <RouterLink class="entry-card entry-card--rose" to="/admin/refunds">
        <span class="entry-card__icon"><AppIcon name="check-badge" :size="20" /></span>
        <span class="entry-card__title">退款审批</span>
        <span class="entry-card__desc">待办：批准或拒绝待审批的退款申请</span>
      </RouterLink>

      <RouterLink class="entry-card entry-card--violet" to="/admin/refund-approvals">
        <span class="entry-card__icon"><AppIcon name="clipboard" :size="20" /></span>
        <span class="entry-card__title">审批记录</span>
        <span class="entry-card__desc">每次决策留下的凭据（审计用）</span>
      </RouterLink>

      <RouterLink class="entry-card entry-card--emerald" to="/admin/refund-records">
        <span class="entry-card__icon"><AppIcon name="wallet" :size="20" /></span>
        <span class="entry-card__title">退款流水</span>
        <span class="entry-card__desc">打款执行结果与失败原因</span>
      </RouterLink>
    </div>
  </div>
</template>
