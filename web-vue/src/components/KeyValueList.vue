<script setup lang="ts">
import { computed } from 'vue'

import type { JsonRecord } from '../types'
import CellValue from './CellValue.vue'
import EmptyState from './EmptyState.vue'
import { humanizeKey } from './value'

/**
 * 一个 JSON 对象 → 键值表。
 * 后端字段还没定，所以**不写死字段名**，直接把返回的对象摊开显示。
 * 等 schema 定稿后再换成显式字段（那样能控制顺序和格式）。
 *
 * `omit` 用来把某些字段摘出去单独渲染 —— 比如订单详情里的 `items` 是个数组，
 * 摊在键值表里只会变成一行挤不下的 JSON，它该有自己的表格。
 */
const props = withDefaults(defineProps<{ data: JsonRecord; omit?: string[] }>(), { omit: () => [] })

const entries = computed(() => Object.entries(props.data).filter(([key]) => !props.omit.includes(key)))
</script>

<template>
  <EmptyState
    v-if="entries.length === 0"
    title="后端返回了空对象"
    hint="接口目前是占位实现（return result.success()），字段还没开始写。"
  />
  <dl v-else class="kv">
    <div v-for="[key, value] in entries" :key="key" class="kv__row">
      <dt class="kv__key">{{ humanizeKey(key) }}</dt>
      <dd class="kv__value"><CellValue :value="value" /></dd>
    </div>
  </dl>
</template>
