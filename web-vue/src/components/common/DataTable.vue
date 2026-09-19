<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import type { JsonRecord } from '../../types'
import CellValue from './CellValue.vue'
import type { Column } from './table'
import { deriveColumns, rowKey } from './table'

const props = withDefaults(
  defineProps<{
    rows: JsonRecord[]
    /** 显式指定列；不传就按数据里的字段自动生成 */
    columns?: Column[]
    /** 用行里的哪个字段拼详情地址，比如 `order_no`（给了才追加"操作"列） */
    detailKey?: string
    detailTo?: (value: string) => string
    detailLabel?: string
  }>(),
  { detailLabel: '查看' },
)

// Vue 里没有"每次渲染重新算一遍"这回事：computed 会缓存，
// 只有 rows/columns 变了才重算 —— React 那边要靠 useMemo 才有的效果，这里默认就有。
const cols = computed(() => props.columns ?? deriveColumns(props.rows))

/**
 * 「查看」链接指向哪。
 *
 * React 版把这一列写成一个返回 JSX 的 `render` 函数；Vue 的列渲染返回的是文本，
 * 塞不进组件，所以"操作"列由表格自己渲染 —— 于是 `Column.render` 可以保持"只返回字符串"，
 * 格式化逻辑不用跟 VNode 混在一起（见 `table.ts` 的注释）。
 */
function linkTarget(row: JsonRecord): string {
  if (!props.detailKey || !props.detailTo) return ''
  const value = row[props.detailKey]
  if (typeof value !== 'string' && typeof value !== 'number') return ''
  return props.detailTo(String(value))
}
</script>

<template>
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th v-for="col in cols" :key="col.key">{{ col.label }}</th>
          <th v-if="detailKey && detailTo">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="rowKey(row, index)">
          <td v-for="col in cols" :key="col.key">
            <!-- cellClass 决定"长什么样"（例如状态列返回 'tag tag--warn'），
                 里面的 CellValue 决定"显示什么"。render 仍然只返回字符串。 -->
            <span :class="col.cellClass?.(row)">
              <CellValue v-if="col.render" :text="col.render(row)" />
              <CellValue v-else :value="row[col.key]" />
            </span>
          </td>
          <td v-if="detailKey && detailTo">
            <RouterLink v-if="linkTarget(row)" class="link" :to="linkTarget(row)">
              {{ detailLabel }}
            </RouterLink>
            <span v-else class="muted">—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
