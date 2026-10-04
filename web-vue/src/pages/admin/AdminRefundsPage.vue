<script setup lang="ts">
import { ref } from 'vue'

import { fetchRefundRequests } from '../../api/admin'
import ResourceListPage from '../../components/common/ResourceListPage.vue'
import { refundStatusCellClass, refundStatusText } from '../../components/refunds/refundTag'
import StubNotice from '../../components/common/StubNotice.vue'
import type { Column } from '../../components/common/table'
import { formatCents, formatDateTime } from '../../components/common/value'

const STATUS_OPTIONS = [
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已批准' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'refunded', label: '已退款' },
  { value: '', label: '全部' },
]

const status = ref('pending')

/**
 * 过滤条件按**函数**交给列表组件，而不是直接传对象。
 *
 * 组件在 effect 里调用它，函数体里读到的 `status` 自动成为依赖 ——
 * 筛选一变请求就重发。传普通对象的话，这边换了新对象也不会触发，
 * 表现就是"点了筛选没反应"。
 *
 * 写成 `<script setup>` 里的具名函数而不是模板里的内联箭头，是因为模板里的
 * `status` 已经被自动解包成字符串了，读不到那个 ref，依赖建立不起来。
 */
const extraQuery = () => ({ status: status.value || undefined })

const COLUMNS: Column[] = [
  { key: 'username', label: '申请人' },
  { key: 'order_no', label: '订单号' },
  { key: 'amount_cents', label: '退款金额', render: (row) => formatCents(row.amount_cents) },
  { key: 'status', label: '状态', render: refundStatusText, cellClass: refundStatusCellClass },
  { key: 'created_at', label: '提交时间', render: (row) => formatDateTime(row.created_at) },
  {
    key: 'request_key',
    label: '申请编号',
    render: (row) => String(row.request_key ?? '').slice(0, 8),
  },
]
</script>

<template>
  <ResourceListPage
    :key="status"
    title="退款审批"
    :fetcher="fetchRefundRequests"
    :columns="COLUMNS"
    :extra-query="extraQuery"
    detail-key="request_key"
    :detail-to="(requestKey: string) => `/admin/refunds/${requestKey}`"
    detail-label="审批"
  >
    待处理的退款申请，默认只看待审批的，可以切换查看其他状态。

    <template #notice>
      <div class="field filter-field">
        <label class="field__label" for="refund-status-filter">查看范围</label>
        <select id="refund-status-filter" v-model="status" class="field__input">
          <option v-for="option in STATUS_OPTIONS" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <StubNotice>
        这里列出的是客户提交的退款申请。只有被处理过的申请才会出现在「审批记录」里，
        切换筛选条件会回到第一页。
      </StubNotice>
    </template>

    <template #empty-hint>
      当前筛选条件下没有申请。待办为空说明所有申请都处理完了。
    </template>
  </ResourceListPage>
</template>
