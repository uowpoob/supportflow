import { fetchOrders } from '../api/admin'
import type { Column } from '../components/DataTable'
import { ResourceListPage } from '../components/ResourceListPage'
import { formatCents, formatDateTime } from '../components/value'
import { FULFILLMENT_STATUS_LABELS, PAYMENT_STATUS_LABELS, labelOf } from '../labels'

/**
 * 列表列：**显式声明**，不用自动推导。
 * 推导出来的列会跟着后端字段走 —— 哪天接口多返回一个 `user_id`，
 * 表头就自己多一列，界面什么时候变的都没人知道。
 */
const COLUMNS: Column[] = [
  { key: 'order_no', label: '订单号' },
  { key: 'username', label: '归属客户' },
  {
    key: 'paid_amount_cents',
    label: '实付金额',
    render: (row) => formatCents(row.paid_amount_cents),
  },
  {
    key: 'payment_status',
    label: '支付状态',
    render: (row) => labelOf(PAYMENT_STATUS_LABELS, row.payment_status),
  },
  {
    key: 'fulfillment_status',
    label: '履约状态',
    render: (row) => labelOf(FULFILLMENT_STATUS_LABELS, row.fulfillment_status),
  },
  {
    key: 'created_at',
    label: '下单时间',
    render: (row) => formatDateTime(row.created_at),
  },
]

/** 全部订单 —— GET /admin/orders */
export function AdminOrdersPage() {
  return (
    <ResourceListPage
      title="订单"
      desc={
        <>
          来自 <code>GET /api/admin/orders?offset=&amp;limit=</code>
          ，含全部客户的订单。点「查看」进入详情核对退款依据。
        </>
      }
      fetcher={fetchOrders}
      columns={COLUMNS}
      detailKey="order_no"
      detailTo={(orderNo) => `/admin/orders/${orderNo}`}
      emptyHint="orders 表还没有数据，先跑 python -m supportflow.db.seed_orders。"
    />
  )
}
