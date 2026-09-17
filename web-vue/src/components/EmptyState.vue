<script setup lang="ts">
/**
 * 请求成功但没有数据。
 * 必须和"后端还没实现"分开表述 —— 否则分不清是页面坏了还是本来就没内容。
 *
 * `hint` 支持两种给法：直接传字符串，或者用 `#hint` 具名插槽塞富文本。
 */
defineProps<{ title: string; hint?: string }>()
</script>

<template>
  <div class="empty-state">
    <p class="empty-state__title">{{ title }}</p>
    <p v-if="hint || $slots.hint" class="empty-state__hint">
      <slot name="hint">{{ hint }}</slot>
    </p>
  </div>
</template>
