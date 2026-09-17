<script setup lang="ts">
import { ref } from 'vue'

import { useApi } from '../composables/useApi'
import type { ListResult, PageQuery } from '../types'
import DataTable from './DataTable.vue'
import EmptyState from './EmptyState.vue'
import ErrorAlert from './ErrorAlert.vue'
import LoadingLine from './LoadingLine.vue'
import Pager from './Pager.vue'
import RawPanel from './RawPanel.vue'
import type { Column } from './table'

const DEFAULT_LIMIT = 10

/**
 * 列表页的公共骨架：请求 → 四种状态（加载中 / 失败可重试 / 空 / 有数据）→ 分页 → 原始返回。
 *
 * 几个列表页都在用它，每个页面自己只剩三件事：标题、请求哪个接口、点哪一列进详情。
 * 想看单个页面的效果，先看 `AdminOrdersPage.vue`（最短）。
 *
 * React 版里 `desc` / `notice` / `emptyHint` 是 `ReactNode` prop；
 * Vue 的等价物是**插槽** —— 页面里直接写标签，组件这边用 `<slot>` 占位。
 */
const props = defineProps<{
  title: string
  fetcher: (query: PageQuery) => Promise<ListResult>
  columns?: Column[]
  detailKey?: string
  detailTo?: (value: string) => string
  detailLabel?: string
  /**
   * 额外的过滤参数，会与 `offset`/`limit` 合并后交给 `fetcher`（例如退款列表的 `status`）。
   *
   * 写成**函数**而不是对象是必要的：只要在 effect 里调用它，
   * 它内部读到的 `ref` 就自动成为依赖，过滤条件一变请求就重发。
   * 传普通对象的话，父组件换了个新对象也不会触发 —— 那种"点了筛选没反应"的 bug 很难查。
   *
   * 切换过滤条件时记得给这个组件加 `:key`，让 `offset` 回到第一页。
   */
  extraQuery?: () => PageQuery
}>()

const offset = ref(0)

// 先取一份非响应式的快照：fetcher 是模块级函数（`fetchOrders` 之类），本来就不会变，
// 但写成 `props.fetcher` 会让它成为 effect 的依赖 —— 父组件重渲染传个新函数就白请求一次。
const doFetch = props.fetcher

// 把 `offset` 传进 fetcher 就算建立了依赖：offset 一变，请求自动重发。
// React 版这里要额外写一个 `[offset]` 依赖数组，Vue 不用。
const { state, data, error, reload } = useApi(() =>
  doFetch({ offset: offset.value, limit: DEFAULT_LIMIT, ...(props.extraQuery?.() ?? {}) }),
)
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <h2 class="page-head__title">{{ title }}</h2>
      <p class="page-head__desc"><slot /></p>
    </header>

    <slot name="notice" />

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="reload" />
    <template v-else-if="state === 'done' && data">
      <EmptyState v-if="data.items.length === 0" title="没有数据">
        <template #hint><slot name="empty-hint" /></template>
      </EmptyState>
      <template v-else>
        <DataTable
          :rows="data.items"
          :columns="columns"
          :detail-key="detailKey"
          :detail-to="detailTo"
          :detail-label="detailLabel"
        />
        <Pager
          :offset="offset"
          :limit="DEFAULT_LIMIT"
          :count="data.items.length"
          :total="data.total"
          @change="offset = $event"
        />
      </template>
      <RawPanel :value="data.raw" />
    </template>
  </div>
</template>
