<script setup lang="ts">
import { computed } from 'vue'

import type { JsonRecord } from '../types'
import DataTable from './DataTable.vue'
import type { Column } from './table'
import { formatCents } from './value'

const ITEM_COLUMNS: Column[] = [
  { key: 'product_name', label: '商品' },
  { key: 'product_model', label: '型号' },
  { key: 'product_code', label: '商品编码' },
  { key: 'quantity', label: '数量' },
  {
    key: 'unit_price_cents',
    label: '单价',
    render: (row) => formatCents(row.unit_price_cents),
  },
  {
    key: 'subtotal_cents',
    label: '小计',
    render: (row) => formatCents(row.subtotal_cents),
  },
]

const props = defineProps<{ data: JsonRecord }>()

const items = computed(() =>
  Array.isArray(props.data.items) ? (props.data.items as JsonRecord[]) : [],
)

/** 明细合计 —— 显示在下面，和订单实付并排，对不上时一眼能看出来。 */
const itemsTotal = computed(() =>
  items.value.reduce(
    (sum, item) => sum + (typeof item.subtotal_cents === 'number' ? item.subtotal_cents : 0),
    0,
  ),
)
</script>

<template>
  <section class="section">
    <h3 class="section__title">商品明细</h3>
    <p v-if="items.length === 0" class="muted">这个订单没有明细记录。</p>
    <template v-else>
      <DataTable :rows="items" :columns="ITEM_COLUMNS" />
      <p class="muted">
        明细合计 {{ formatCents(itemsTotal) || '—' }}，订单实付
        {{ formatCents(data.paid_amount_cents) || '—' }}
      </p>
    </template>
  </section>
</template>
