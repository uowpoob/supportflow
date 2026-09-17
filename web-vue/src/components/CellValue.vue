<script setup lang="ts">
import { computed } from 'vue'

import { renderValue } from './value'

/**
 * 表格 / 键值表里"一格"的统一渲染。
 *
 * 存在意义：**把"空值怎么显示"收敛到一个地方**。
 * 格式化函数（`formatCents` / `formatDateTime`）空值一律返回空字符串，
 * 这里看到空字符串就渲染灰色破折号；对象则包在 `<code>` 里，免得 JSON 撑破版面。
 */
const props = defineProps<{
  /** 原始值（与 `text` 二选一） */
  value?: unknown
  /** 已经格式化好的文本，优先级高于 `value` */
  text?: string
}>()

const isObjectValue = computed(
  () => props.text === undefined && props.value !== null && typeof props.value === 'object',
)

const display = computed(() => (props.text !== undefined ? props.text : renderValue(props.value)))
</script>

<template>
  <span v-if="display === ''" class="muted">—</span>
  <code v-else-if="isObjectValue">{{ display }}</code>
  <span v-else>{{ display }}</span>
</template>
