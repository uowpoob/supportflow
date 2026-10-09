<script setup lang="ts">
import type { Conversation } from '../../types'
import AppIcon from '../common/AppIcon.vue'

/**
 * 侧栏的会话列表。
 *
 * 只负责"画出来 + 告诉你点了哪个 / 删了哪个"，一个请求都不发 ——
 * 数据从哪来、什么时候重新拉、删完之后怎么收尾，全在页面里，这样只有一处需要看。
 *
 * 全部会话都列出来，一条不删；会话攒多了由**外面那个独立盒子**（`.side-scroll`，
 * 自带边框底色、`flex: 1` + `overflow-y: auto`）自己上下滚。左栏高度不变，右栏底边永远和它齐平。
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

const emit = defineEmits<{ select: [id: string]; remove: [id: string] }>()

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
  <!-- 独立滚动容器：会话再多也只在这个盒子里面上下拖。
       它自己有边界、有高度上限 —— 既不撑长左栏，也不会让整个页面跟着滚。 -->
  <div class="side-scroll">
    <div v-if="items.length === 0" class="side-empty">
      <p>还没有会话</p>
      <p class="muted">在右边输入你的问题，发送后会自动开一个。</p>
    </div>

    <ul v-else class="side-list">
      <li v-for="item in items" :key="item.id" class="side-list__item side-list__item--flush">
        <div class="side-list__row">
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
          <!-- 删除按钮：只有鼠标停在这一行才露出来，平时列表保持干净。
               `@click.stop` 挡住冒泡 —— 点它只删这一条，不会顺带把会话选中。 -->
          <button
            type="button"
            class="side-list__remove"
            title="删除会话"
            aria-label="删除会话"
            :disabled="disabled"
            @click.stop="emit('remove', item.id)"
          >
            <AppIcon name="trash" :size="15" />
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
/* 会话行改成「按钮 + 删除」的横向排布：删除按钮平时透明、悬停才显形。 */
.side-list__row {
  position: relative;
}

/* 删除按钮贴右边、垂直居中，占的位置很小，不挤占会话标题的空间。 */
.side-list__remove {
  position: absolute;
  top: 50%;
  right: 4px;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #9aa4b2;
  cursor: pointer;
  opacity: 0;
  transition: background 0.15s, color 0.15s, opacity 0.15s;
}

.side-list__row:hover .side-list__remove {
  opacity: 1;
}

.side-list__row:focus-within .side-list__remove {
  opacity: 1;
}

.side-list__remove:hover:not(:disabled) {
  background: #fdecec;
  color: var(--danger);
}

.side-list__remove:disabled {
  cursor: not-allowed;
}

/* 有删除按钮占着右边，标题别跟它叠上：给按钮留出空间。 */
.side-list__row .side-list__btn {
  padding-right: 32px;
}
</style>
