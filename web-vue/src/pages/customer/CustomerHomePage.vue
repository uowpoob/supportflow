<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { fetchConversations } from '../../api/customer'
import { useAuth } from '../../auth/useAuth'
import { useApi } from '../../composables/useApi'
import PlaceholderBlock from '../../layouts/PlaceholderBlock.vue'
import type { JsonRecord } from '../../types'

/** 客户首页：快捷入口 + 左侧会话列表 + 右侧对话区。
 *  消息流等 Agent 接上再填；会话列表已经接了真实接口。 */
const { user } = useAuth()
const { state, data, error, reload } = useApi(() => fetchConversations())

/** 侧栏里一行会话 —— 字段还没定，先把能认出来的那个当标题。 */
function conversationLabel(item: JsonRecord, index: number): string {
  for (const key of ['title', 'subject', 'conversation_no', 'order_no', 'id']) {
    const value = item[key]
    if (typeof value === 'string' || typeof value === 'number') return String(value)
  }
  return `会话 ${index + 1}`
}
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <h2 class="page-head__title">你好，{{ user?.username }}</h2>
      <p class="page-head__desc">可以查询订单、咨询售后政策、提交退款申请。</p>
    </header>

    <div class="card-grid">
      <RouterLink class="entry-card" to="/customer/orders">
        <span class="entry-card__title">我的订单</span>
        <span class="entry-card__desc">查看订单详情与退款资格</span>
      </RouterLink>
      <RouterLink class="entry-card" to="/customer/refund-requests">
        <span class="entry-card__title">我的退款申请</span>
        <span class="entry-card__desc">查看申请进度与审批意见</span>
      </RouterLink>
    </div>

    <div class="chat-layout">
      <aside class="chat-layout__side">
        <div class="side-head">会话</div>

        <div v-if="state === 'loading'" class="side-empty">
          <p class="muted">加载中…</p>
        </div>

        <div v-else-if="state === 'error'" class="side-empty">
          <p class="muted">{{ error }}</p>
          <button type="button" class="btn btn--ghost btn--sm" @click="reload">重试</button>
        </div>

        <template v-else-if="state === 'done' && data">
          <div v-if="data.items.length === 0" class="side-empty">
            <p>还没有会话</p>
            <p class="muted">
              接口 <code>GET /api/customer/conversations</code> 已接上，后端暂无数据。
            </p>
          </div>
          <ul v-else class="side-list">
            <li v-for="(item, index) in data.items" :key="index" class="side-list__item">
              {{ conversationLabel(item, index) }}
            </li>
          </ul>
        </template>
      </aside>

      <section class="chat-layout__main">
        <div class="chat-empty">
          <p class="chat-empty__title">对话区</p>
          <p class="muted">提问后在这里显示消息流（后续接入 SSE 流式输出）。</p>
        </div>

        <form class="composer" @submit.prevent>
          <input class="composer__input" placeholder="对话接口尚未实现，暂时无法发送" disabled />
          <button type="submit" class="btn btn--primary" disabled>发送</button>
        </form>
      </section>
    </div>

    <PlaceholderBlock title="下一步会做什么">
      <ul class="plain-list">
        <li>接入会话与消息接口，会话列表可点击切换。</li>
        <li>接 SSE 流式返回，断开后用事件 ID 或状态查询恢复，不重复执行业务操作。</li>
      </ul>
    </PlaceholderBlock>
  </div>
</template>
