<script setup lang="ts">
import { RETRIEVAL_STATUS_LABELS, labelOf } from '../../labels'
import type { RetrievalStatus, RetrievedSource } from '../../types'

/**
 * 本轮的检索依据 —— 属于"这一轮"，不混进消息列表里。
 *
 * 这是**候选来源**，不代表助手真的引用了每一条；业务类问题（查订单、提退款）
 * 通常根本不触发检索，`status` 会是 `not_requested`。
 *
 * `score` 只显示、不参与判断：它是融合分或重排分，**不能跨查询比较**
 * （同一批里排个序可以，拿它跟别的提问比大小没有意义），
 * 所以这里不用"分数低于多少就标红"这类规则。
 */
defineProps<{
  status: RetrievalStatus
  sources: RetrievedSource[]
}>()

/** 配色按"这个状态意味着什么"选：蓝=有结果、黄=没等到、红=坏了。 */
const TONE: Record<string, string> = {
  ready: 'tag--info',
  empty: 'tag--warn',
  unavailable: 'tag--danger',
  not_requested: 'tag--muted',
}

function toneOf(status: RetrievalStatus): string {
  return TONE[status] ?? 'tag--muted'
}

/** 分数是 0~1 的小数，留三位足够看；`score` 为空时整段不显示。 */
function scoreLabel(score: number | null): string {
  return score === null ? '' : `分数 ${score.toFixed(3)}`
}
</script>

<template>
  <div class="evidence">
    <p class="evidence__head">
      <span class="tag" :class="toneOf(status)">{{ labelOf(RETRIEVAL_STATUS_LABELS, status) }}</span>
      <span class="muted">
        {{ sources.length }} 条候选依据，只表示检索命中，不代表助手逐条引用
      </span>
    </p>

    <ol v-if="sources.length" class="evidence__list">
      <li v-for="item in sources" :key="item.chunk_id">
        <span class="evidence__title">{{ item.title }}</span>
        <span v-if="item.section" class="muted"> · {{ item.section }}</span>
        <span class="evidence__source">{{ item.source }}</span>
        <span v-if="item.score !== null" class="muted"> {{ scoreLabel(item.score) }}</span>
      </li>
    </ol>
  </div>
</template>
