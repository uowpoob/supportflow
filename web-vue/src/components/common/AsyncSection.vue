<script setup lang="ts">
import { useApi } from '../../composables/useApi'
import type { JsonRecord } from '../../types'
import ErrorAlert from './ErrorAlert.vue'
import KeyValueList from './KeyValueList.vue'
import LoadingLine from './LoadingLine.vue'
import RawPanel from './RawPanel.vue'

/**
 * 详情页里的附加区块（例如订单详情下的"退款资格"）。
 * 跟主数据各发各的请求、各自管三种状态，一块坏了不影响另一块。
 */
const props = defineProps<{ title: string; fetcher: () => Promise<JsonRecord> }>()

const { state, data, error, reload } = useApi(props.fetcher)
</script>

<template>
  <section class="section">
    <h3 class="section__title">{{ title }}</h3>
    <slot name="notice" />

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="reload" />
    <template v-else-if="state === 'done' && data">
      <KeyValueList :data="data" />
      <RawPanel :value="data" label="这个区块的原始返回" />
    </template>
  </section>
</template>
