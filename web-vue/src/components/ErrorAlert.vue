<script setup lang="ts">
/**
 * 请求失败：带重试按钮，否则用户只能刷整页。
 *
 * React 把 `onRetry` 当 prop 传进来；Vue 里改成 emit `retry` 事件，
 * 模板里就是 `<ErrorAlert :message="error" retryable @retry="reload" />`。
 */
defineProps<{ message: string; retryable?: boolean }>()
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="alert alert--error alert--row">
    <span>{{ message }}</span>
    <button v-if="retryable" type="button" class="btn btn--ghost btn--sm" @click="emit('retry')">
      重试
    </button>
  </div>
</template>
