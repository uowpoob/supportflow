<script setup lang="ts">
import type { JsonRecord } from '../types'
import { formatDateTime } from './value'

/** 时间线字段：主键值表里摘出来单独排版，ISO 原文（带微秒）没法看。 */
const TIMELINE: [key: string, label: string][] = [
  ['created_at', '下单时间'],
  ['paid_at', '支付时间'],
  ['shipped_at', '发货时间'],
  ['delivered_at', '签收时间'],
]

defineProps<{ data: JsonRecord }>()
</script>

<template>
  <section class="section">
    <h3 class="section__title">时间线</h3>
    <dl class="kv">
      <div v-for="[key, label] in TIMELINE" :key="key" class="kv__row">
        <dt class="kv__key">{{ label }}</dt>
        <dd class="kv__value">{{ formatDateTime(data[key]) || '—' }}</dd>
      </div>
    </dl>
  </section>
</template>
