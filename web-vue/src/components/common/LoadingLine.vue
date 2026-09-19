<script setup lang="ts">
/** 加载中。 */
withDefaults(defineProps<{ label?: string }>(), { label: '加载中…' })
</script>

<template>
  <p class="muted">{{ label }}</p>
</template>
