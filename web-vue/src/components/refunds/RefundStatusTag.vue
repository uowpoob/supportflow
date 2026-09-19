<script setup lang="ts">
import { computed } from 'vue'

import { REFUND_STATUS_LABELS, labelOf } from '../../labels'
import { refundStatusTone } from './refundTag'

/**
 * 退款**申请**状态徽章（`refund_requests.status`）。
 *
 * 配色不在这个组件里定义 —— 从 `refundTag.ts` 取，跟表格列用的是同一张表。
 * 否则同一个"待审批"在列表里是黄的、在详情里可能是蓝的，那种不一致没人会注意到，
 * 但它确实在传达错误的优先级。
 *
 * ⚠️ 别拿它显示 `refund_records.status`（执行结果）—— 那是**另一个枚举**，
 * 只是字段名碰巧也叫 `status`。执行结果走 `refundExecutionTone()`。
 */
const props = defineProps<{ status: unknown }>()

const tone = computed(() => refundStatusTone(props.status))
const text = computed(() => labelOf(REFUND_STATUS_LABELS, props.status))
</script>

<template>
  <span class="tag" :class="tone">{{ text }}</span>
</template>
