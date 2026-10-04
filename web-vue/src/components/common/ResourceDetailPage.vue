<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { useApi } from '../../composables/useApi'
import type { JsonRecord } from '../../types'
import ErrorAlert from './ErrorAlert.vue'
import KeyValueList from './KeyValueList.vue'
import LoadingLine from './LoadingLine.vue'

/**
 * 详情页的公共骨架：一个 JSON 对象 → 键值表 + 返回列表的链接。
 * 后端字段没定，所以不写死字段名，直接把返回的对象摊开（见 `KeyValueList`）。
 *
 * ---
 * 三个插槽，对应 React 版的三个 prop（`actions` / `extra` / `renderExtra`）：
 *
 * | 插槽 | 对应 React | 拿到什么 | 出现在哪 |
 * |---|---|---|---|
 * | `#actions` | `actions` | 作用域给出 `data` / `state` / `reload` | 最下方，操作按钮区 |
 * | `#extra`   | `extra`   | 否 | 操作区**上方**（比如"退款资格"判定结论）|
 * | `#data-extra` | `renderExtra` | **是**（作用域插槽给出 `data`）| 键值表正下方 |
 *
 * `extra` 排在 `actions` **之前**是刻意的：它是"结论"，`actions` 是"动作"。
 * 反过来的话，用户会先看到一个能点的按钮，点了才知道自己其实不符合条件 ——
 * 顺序错了就是错的，不是审美问题。
 *
 * `renderExtra` 在 React 里是个"吃 data、吐 JSX"的函数；Vue 的对应物就是作用域插槽 ——
 * 所以 `AdminOrderDetailPage` 里那几个依赖主数据的区块（时间线、商品明细）走 `#data-extra`。
 *
 * `#actions` 是**唯一**能把 `reload` 拿出去的插槽，因为"提交成功后刷新本页数据"
 * 这件事只有操作区才需要（比如管理员批准完要立刻看到新状态）。
 * 它渲染在 `v-if` 之外，所以 `data` 在加载完成前是 `null` —— 用到的页面自己判一下。
 */
const props = withDefaults(
  defineProps<{
    title: string
    fetcher: () => Promise<JsonRecord>
    backTo: string
    backLabel?: string
    /** 从主数据的键值表里摘出去的字段，交给 `#data-extra` 单独渲染 */
    omitKeys?: string[]
  }>(),
  { backLabel: '返回列表' },
)

// 有意不写成 `() => props.fetcher()`：那样 `props.fetcher` 会成为 effect 的依赖，
// 父组件每次重渲染传进来的新函数都会白触发一次请求。
// 详情页的 fetcher 只跟路由参数有关，而它在组件挂载时就是固定的。
const { state, data, error, reload } = useApi(props.fetcher)
</script>

<template>
  <div class="stack">
    <header class="page-head">
      <p class="crumbs">
        <RouterLink class="link" :to="backTo">← {{ backLabel }}</RouterLink>
      </p>
      <h2 class="page-head__title">{{ title }}</h2>
      <p class="page-head__desc"><slot /></p>
    </header>

    <slot name="notice" />

    <LoadingLine v-if="state === 'loading'" />
    <ErrorAlert v-else-if="state === 'error'" :message="error" retryable @retry="reload" />
    <template v-else-if="state === 'done' && data">
      <KeyValueList :data="data" :omit="omitKeys" />
      <slot name="data-extra" :data="data" />
    </template>

    <!-- 先结论（资格判定），后动作（提交表单）—— 见上面注释里的理由 -->
    <slot name="extra" />
    <slot name="actions" :data="data" :state="state" :reload="reload" />
  </div>
</template>
