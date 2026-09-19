<script setup lang="ts">
import { RouterLink } from 'vue-router'

import PlaceholderBlock from '../../layouts/PlaceholderBlock.vue'
</script>

<template>
  <!-- 管理员首页：四个功能区入口。 -->
  <div class="stack">
    <header class="page-head">
      <h2 class="page-head__title">管理后台</h2>
      <p class="page-head__desc">查看订单、处理退款审批、查审批记录与退款流水。</p>
    </header>

    <div class="card-grid">
      <RouterLink class="entry-card" to="/admin/orders">
        <span class="entry-card__title">订单</span>
        <span class="entry-card__desc">查看全部订单，进详情核对退款依据</span>
      </RouterLink>

      <RouterLink class="entry-card" to="/admin/refunds">
        <span class="entry-card__title">退款审批</span>
        <span class="entry-card__desc">待办：批准或拒绝待审批的退款申请</span>
      </RouterLink>

      <RouterLink class="entry-card" to="/admin/refund-approvals">
        <span class="entry-card__title">审批记录</span>
        <span class="entry-card__desc">每次决策留下的凭据（审计用）</span>
      </RouterLink>

      <RouterLink class="entry-card" to="/admin/refund-records">
        <span class="entry-card__title">退款流水</span>
        <span class="entry-card__desc">打款执行结果与失败原因</span>
      </RouterLink>
    </div>

    <PlaceholderBlock title="接口现状">
      <ul class="plain-list">
        <li>
          订单列表与详情（<code>GET /api/admin/orders</code>、
          <code>/orders/&#123;order_no&#125;</code>）<strong>已经接上真实数据</strong>；
          退款申请、审批记录、退款流水三个接口后端仍是占位实现，页面显示空状态。
        </li>
        <li>
          审批（批准 / 拒绝）和客户提交申请这两个<strong>写操作</strong>只在界面上留了位置、按钮禁用，
          等请求体定稿再打开。
        </li>
      </ul>
    </PlaceholderBlock>
  </div>
</template>
