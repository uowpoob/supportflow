<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'

import type { ChatMessage } from '../../types'

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
  /** 正在等本轮回复 */
  pending?: boolean
  /** 刚发出去、还没落库的那句话，先显示出来 */
  optimistic?: string
}>()

const scroller = ref<HTMLElement | null>(null)

/** 滚到底。`nextTick` 不能省：要等 DOM 按新数据更新完，`scrollHeight` 才是新高度。 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  const element = scroller.value
  if (element) element.scrollTop = element.scrollHeight
}

// 消息一变就滚到底 —— 最新的一条总在视野里。
watch(() => [props.messages.length, props.pending, props.optimistic], scrollToBottom)

// 刚打开一个会话时也要在底部（此时消息是"已存在"的，上面的 watch 不会触发）。
onMounted(scrollToBottom)
</script>

<template>
  <div ref="scroller" class="chat-thread">
    <p
      v-if="messages.length === 0 && !optimistic && !pending"
      class="muted chat-thread__hint"
    >
      这个会话还没有消息。在下面提问，Agent 会先看你的订单和退款情况，再决定要不要查知识库。
    </p>

    <!-- `:key` 用消息 id 而不是下标：追加消息时下标会整体挪位，Vue 会认错元素。 -->
    <div
      v-for="message in messages"
      :key="message.id"
      class="bubble-row"
      :class="`bubble-row--${message.role}`"
    >
      <div class="bubble" :class="`bubble--${message.role}`">{{ message.content }}</div>
    </div>

    <div v-if="optimistic" class="bubble-row bubble-row--user">
      <div class="bubble bubble--user bubble--pending">{{ optimistic }}</div>
    </div>

    <div v-if="pending" class="bubble-row bubble-row--assistant">
      <div class="bubble bubble--assistant bubble--pending">正在回复…</div>
    </div>
  </div>
</template>
