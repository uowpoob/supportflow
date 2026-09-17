<script setup lang="ts">
/** 尚未实现的区域的统一占位块，避免看起来像"坏了"。 */
defineProps<{ title: string }>()
</script>

<template>
  <section class="placeholder">
    <h3 class="placeholder__title">{{ title }}</h3>
    <!-- 不传内容时走默认文案，对应 React 版的 `children ?? '此区域留待后续步骤填充。'` -->
    <div class="placeholder__body"><slot>此区域留待后续步骤填充。</slot></div>
  </section>
</template>
