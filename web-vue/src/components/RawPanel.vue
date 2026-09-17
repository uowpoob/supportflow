<script setup lang="ts">
import { computed } from 'vue'

/** 后端响应结构未定稿期间，把原始返回折叠出来，方便对着字段改页面。 */
const props = withDefaults(defineProps<{ value: unknown; label?: string }>(), {
  label: '接口原始返回',
})

const text = computed(() => JSON.stringify(props.value, null, 2) ?? 'null')
</script>

<template>
  <details class="raw">
    <summary class="raw__summary">{{ label }}</summary>
    <pre class="codeblock">{{ text }}</pre>
  </details>
</template>
