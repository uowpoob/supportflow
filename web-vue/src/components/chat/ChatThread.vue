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
  /** 正在等本轮回复（还没拿到第一个字） */
  pending?: boolean
  /** 刚发出去、还没落库的那句话，先显示出来 */
  optimistic?: string
  /**
   * 流式进行中的助手文字，**逐字增长**。
   *
   * 它跟 `messages` 是两回事：`messages` 里的东西服务端已经存好了，
   * 而这个只是屏幕上暂时长出来的草稿 —— 本轮结束（`done` 事件）时会整段
   * 被服务端返回的消息替换掉，所以不用也不能在这里给它 id。
   */
  streaming?: string
  /**
   * 后端说这个会话正有一轮在跑，但**这个浏览器不是发起方** ——
   * 典型场景是发送过程中刷新了页面，连接断了而服务端还在继续。
   *
   * 跟 `pending` 的区别：`pending` 是本页自己发的请求在等回音（能等到 `done`），
   * 这里等不到任何东西，只能靠重新读历史发现结果。
   * 两者可能同时为真（切走再切回来的那一小会儿），所以文案让它们一致、不互相覆盖。
   */
  runningElsewhere?: boolean
}>()

const scroller = ref<HTMLElement | null>(null)

/** 滚到底。`nextTick` 不能省：要等 DOM 按新数据更新完，`scrollHeight` 才是新高度。 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  const element = scroller.value
  if (element) element.scrollTop = element.scrollHeight
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
    <p
      v-if="messages.length === 0 && !optimistic && !pending && !streaming && !runningElsewhere"
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

    <!-- 流式输出中：已经吐出来的字。等 `done` 事件回来时下面那个会变成正式消息。 -->
    <div v-if="streaming" class="bubble-row bubble-row--assistant">
      <div class="bubble bubble--assistant bubble--pending">{{ streaming }}</div>
    </div>

    <!-- 还没拿到第一个字。已经流式出字之后就不再显示它，否则会跟上面的草稿重复。 -->
    <div v-if="(pending || runningElsewhere) && !streaming" class="bubble-row bubble-row--assistant">
      <div class="bubble bubble--assistant bubble--pending">
        {{ runningElsewhere ? '正在回复（页面刷新过，完成后会出现在这里）' : '正在回复…' }}
      </div>
    </div>
  </div>
</template>
