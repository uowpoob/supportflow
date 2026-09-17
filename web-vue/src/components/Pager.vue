<script setup lang="ts">
import { computed } from 'vue'

/**
 * 分页条。后端用 offset/limit。
 * 拿不到总数时，用"本页是否满页"来推断有没有下一页 —— 不够准，但不会点不动。
 */
const props = defineProps<{
  offset: number
  limit: number
  count: number
  /** 总数。后端没给时不传，靠 count >= limit 猜有没有下一页 */
  total?: number
}>()

// React 版是把 `onChange` 当 prop 传下来；Vue 的习惯是 emit 事件。
// 模板里写 `@change="setOffset"`，父组件收到的还是同一个数字。
const emit = defineEmits<{ change: [offset: number] }>()

const hasPrev = computed(() => props.offset > 0)
const hasNext = computed(() =>
  props.total !== undefined ? props.offset + props.count < props.total : props.count >= props.limit,
)
const range = computed(() =>
  props.count === 0 ? '本页没有数据' : `第 ${props.offset + 1}–${props.offset + props.count} 条`,
)
</script>

<template>
  <div class="pager">
    <span class="muted">{{ range }}<template v-if="total !== undefined"> / 共 {{ total }} 条</template></span>
    <div class="pager__actions">
      <button
        type="button"
        class="btn btn--ghost btn--sm"
        :disabled="!hasPrev"
        @click="emit('change', Math.max(0, offset - limit))"
      >
        上一页
      </button>
      <button
        type="button"
        class="btn btn--ghost btn--sm"
        :disabled="!hasNext"
        @click="emit('change', offset + limit)"
      >
        下一页
      </button>
    </div>
  </div>
</template>
