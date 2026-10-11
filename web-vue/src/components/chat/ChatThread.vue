<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'

import type { ChatMessage } from '../../types'
import AppIcon from '../common/AppIcon.vue'

/**
 * 消息流。
 *
 * 两条约定（和后端的契约对齐，不要在这里"顺手"加工）：
 * 1. **数组顺序就是显示顺序** —— 后端已按对话顺序排好，别按 id 或时间重排。
 * 2. **`role` 只决定长什么样**，决定不了内容是什么。两边都是同一个 `{{ content }}`，
 *    只是挂的 class 不同。内容一律当纯文本插值（`v-html` 会把模型输出当 HTML 执行）。
 */
const props = defineProps<{
  messages: ChatMessage[]
  /** 正在等本轮回复（还没拿到第一个字） */
  pending?: boolean
  /** 刚发出去、还没落库的那句话，先显示出来 */
  optimistic?: string
  /** SSE 增量或历史接口恢复的助手草稿，完成后由正式消息替换。 */
  streaming?: string
  /** 后台运行中，当前页面通过轮询快照恢复进度。 */
  runningElsewhere?: boolean
}>()

const scroller = ref<HTMLElement | null>(null)
const emit = defineEmits<{ suggest: [text: string] }>()
const suggestions = [
  { icon: 'box', title: '查询订单', text: '帮我查询最近的订单' },
  { icon: 'search', title: '了解售后政策', text: '我想了解商品的退换货政策' },
  { icon: 'receipt', title: '申请退款', text: '我想申请退款，需要满足什么条件？' },
]

/** 滚到底。`nextTick` 不能省：要等 DOM 按新数据更新完，`scrollHeight` 才是新高度。 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  const element = scroller.value
  if (element) {
    const hasContent = props.messages.length > 0 || props.optimistic || props.pending || props.streaming || props.runningElsewhere
    element.scrollTop = hasContent ? element.scrollHeight : 0
  }
}

// 消息一变就滚到底 —— 最新的那条总在视野里。
// ⚠️ `streaming` 也要盯着：逐字增长时高度一直在变，不滚的话新字会顶到视野外面。
watch(
  () => [
    props.messages.length, props.pending, props.optimistic, props.streaming,
    props.runningElsewhere,
  ],
  scrollToBottom,
)

// 刚打开一个会话时也要在底部（此时消息是"已存在"的，上面的 watch 不会触发）。
onMounted(scrollToBottom)
</script>

<template>
  <div ref="scroller" class="chat-thread">
    <div
      v-if="messages.length === 0 && !optimistic && !pending && !streaming && !runningElsewhere"
      class="chat-welcome"
    >
      <span class="chat-welcome__icon"><AppIcon name="robot" :size="32" /></span>
      <span class="eyebrow">你的智能售后助手</span>
      <h3>有什么可以帮你？</h3>
      <p>查询订单、解答售后疑问、协助退款申请。<br />从一个问题开始，我会帮你理清下一步。</p>
      <div class="chat-suggestions">
        <button v-for="item in suggestions" :key="item.title" type="button" class="suggestion" @click="emit('suggest', item.text)">
          <AppIcon :name="item.icon" :size="20" /><strong>{{ item.title }}</strong><span>{{ item.text }}</span><i aria-hidden="true">↗</i>
        </button>
      </div>
    </div>

    <!-- `:key` 用消息 id 而不是下标：追加消息时下标会整体挪位，Vue 会认错元素。 -->
    <div
      v-for="message in messages"
      :key="message.id"
      class="bubble-row"
      :class="`bubble-row--${message.role}`"
    >
      <span class="bubble-avatar" :class="`bubble-avatar--${message.role}`">
        <AppIcon :name="message.role === 'user' ? 'user' : 'robot'" :size="16" />
      </span>
      <div class="bubble" :class="`bubble--${message.role}`">{{ message.content }}</div>
    </div>

    <div v-if="optimistic" class="bubble-row bubble-row--user">
      <span class="bubble-avatar bubble-avatar--user">
        <AppIcon name="user" :size="16" />
      </span>
      <div class="bubble bubble--user bubble--pending">{{ optimistic }}</div>
    </div>

    <!-- 流式输出中：已经吐出来的字。等 `done` 事件回来时下面那个会变成正式消息。 -->
    <div v-if="streaming" class="bubble-row bubble-row--assistant">
      <span class="bubble-avatar bubble-avatar--assistant">
        <AppIcon name="robot" :size="16" />
      </span>
      <div class="bubble bubble--assistant bubble--pending">{{ streaming }}</div>
    </div>

    <!-- 还没拿到第一个字。已经流式出字之后就不再显示它，否则会跟上面的草稿重复。 -->
    <div v-if="(pending || runningElsewhere) && !streaming" class="bubble-row bubble-row--assistant">
      <span class="bubble-avatar bubble-avatar--assistant">
        <AppIcon name="robot" :size="16" />
      </span>
      <div class="bubble bubble--assistant bubble--pending">
        {{ runningElsewhere ? '正在回复，已恢复后台运行进度…' : '正在回复…' }}
      </div>
    </div>
  </div>
</template>
