<script setup lang="ts">
import { RETRIEVAL_STATUS_LABELS, labelOf } from '../../labels'
import type { RetrievalStatus, RetrievedSource, WebSearchStatus, WebSource } from '../../types'

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
  webStatus: WebSearchStatus
  webSources: WebSource[]
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

/**
 * 分数 → 相关度档位。
 *
 * 界面上只给"高/中/低"、不给 `0.823` 这种原始分：分数要么来自融合排序、要么来自重排模型，
 * **不能跨查询比较**，摆给用户既看不懂也没法用。阈值只管呈现，不参与任何判断。
 */
const RELEVANCE: [min: number, label: string][] = [
  [0.7, '相关度 高'],
  [0.4, '相关度 中'],
]

/** `score` 为空时整段不显示。 */
function relevanceLabel(score: number | null): string {
  if (score === null) return ''
  for (const [min, label] of RELEVANCE) {
    if (score >= min) return label
  }
  return '相关度 低'
}

function sourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined
  } catch { return undefined }
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
        <span v-if="item.score !== null" class="muted"> {{ relevanceLabel(item.score) }}</span>
      </li>
    </ol>

    <p v-if="status === 'empty' || status === 'unavailable'" class="muted">
      本地知识库未找到足以回答问题的资料{{ status === 'unavailable' ? '（检索服务暂不可用）' : '' }}。
      <template v-if="webStatus === 'ready'">以下内容参考网上公开信息，请通过来源链接核对。</template>
      <template v-else-if="webStatus === 'unavailable'">当前联网搜索不可用；模型的通用建议未经联网核实。</template>
      <template v-else-if="webStatus === 'empty'">联网搜索也未找到可用资料；模型的通用建议未经联网核实。</template>
    </p>
    <p v-if="webStatus === 'ready' && webSources.length" class="muted">
      网上信息可能不准确或已过时，请核对来源、发布日期和适用型号，优先以官方说明书或官方客服确认为准。
    </p>
    <ol v-if="webSources.length" class="evidence__list">
      <li v-for="item in webSources" :key="item.url">
        <a v-if="sourceUrl(item.url)" :href="sourceUrl(item.url)" target="_blank" rel="noopener noreferrer">
          {{ item.title || item.url }}
        </a>
        <span v-else>{{ item.title }}</span>
        <span class="evidence__source">网上公开信息</span>
      </li>
    </ol>
  </div>
</template>
