<script setup lang="ts">
import { RouterLink } from 'vue-router'

import AppIcon from '../../components/common/AppIcon.vue'
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <div class="eyebrow">ADMIN WORKSPACE</div>
      <h2 class="page-head__title">管理后台</h2>
      <p class="page-head__desc">查看订单、处理退款审批、查审批记录与退款流水。</p>
    </header>

    <section class="admin-banner">
      <div><span class="eyebrow">售后管理，有条不紊</span><h3>让每一笔申请，都得到妥善处理。</h3><p>核对订单、处理审批、追踪退款，在一个工作台中完成。</p><RouterLink class="btn btn--primary btn--icon" to="/admin/refunds">前往退款审批 <span aria-hidden="true">→</span></RouterLink></div>
      <AppIcon name="check-badge" :size="120" />
    </section>

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
    <section class="card workflow">
      <h3 class="section__title">售后处理流程</h3>
      <p class="muted">沿着业务流程核对信息，处理结果随时可追溯。</p>
      <ol class="workflow__steps">
        <li><span>01</span><strong>核对订单</strong><p>查看商品、支付与签收信息</p></li>
        <li><span>02</span><strong>审批申请</strong><p>确认退款依据与申请原因</p></li>
        <li><span>03</span><strong>跟进退款</strong><p>查看执行结果与失败原因</p></li>
        <li><span>04</span><strong>追溯记录</strong><p>核查审批意见与处理凭据</p></li>
      </ol>
    </section>
  </div>
</template>
