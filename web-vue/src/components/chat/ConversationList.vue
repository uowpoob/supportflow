<script setup lang="ts">
import type { Conversation } from '../../types'

/**
 * 侧栏的会话列表。
 *
 * 只负责"画出来 + 告诉你点了哪个"，一个请求都不发 ——
 * 数据从哪来、什么时候重新拉，全在页面里，这样只有一处需要看。
 */
defineProps<{
  items: Conversation[]
  /** 当前正在看的会话；没有选中时传 null */
  selectedId: string | null
  /** 本轮对话正在跑的时候不许切走 —— 结果要贴回发起时那个会话 */
  disabled?: boolean
  /**
   * 正在等管理员审批的会话 id。
   *
   * 只有**服务端确认过**的会话才会进这个集合（发送时带的 `status`，或进来后读历史得到的）。
   * 不猜：会话列表接口没有这个信息，没进过会话的就不知道。
   */
  waitingIds?: string[]
}>()

const emit = defineEmits<{ select: [id: string] }>()

/**
 * `updated_at` 是后端发来的 UTC 时间（结尾带 Z），`toLocaleString` 会按浏览器所在时区显示。
 * 解析失败就给空串 —— 宁可少显示一行，也别在界面上出现 "Invalid Date"。
 */
function timeLabel(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div v-if="items.length === 0" class="side-empty">
    <p>还没有会话</p>
    <p class="muted">点上面的「+ 新建」开一个，然后在右边提问。</p>
  </div>

  <ul v-else class="side-list">
    <li
      v-for="item in items"
      :key="item.id"
      class="side-list__item side-list__item--flush"
    >
      <button
        type="button"
        class="side-list__btn"
        :class="{ 'side-list__btn--active': item.id === selectedId }"
        :disabled="disabled"
        @click="emit('select', item.id)"
      >
        <span class="side-list__title">{{ item.title }}</span>
        <!-- 等待审批 = 这一轮卡住了，必须让它在列表里就能被看见，不用点进去才知道。 -->
        <span v-if="waitingIds?.includes(item.id)" class="side-list__badge">等审批</span>
        <span class="side-list__time">{{ timeLabel(item.updated_at) }}</span>
      </button>
    </li>
  </ul>
</template>
