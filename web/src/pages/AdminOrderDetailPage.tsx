import { useParams } from 'react-router-dom'

import { fetchOrder } from '../api/admin'
import type { Column } from '../components/DataTable'
import { DataTable } from '../components/DataTable'
import { ResourceDetailPage } from '../components/ResourceDetailPage'
import { formatCents, formatDateTime } from '../components/value'
import type { JsonRecord } from '../types'

/** 时间线字段：主键值表里摘出来单独排版，ISO 原文（带微秒）没法看。 */
const TIMELINE: [key: string, label: string][] = [
  ['created_at', '下单时间'],
  ['paid_at', '支付时间'],
  ['shipped_at', '发货时间'],
  ['delivered_at', '签收时间'],
]

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

function OrderTimeline({ data }: { data: JsonRecord }) {
  return (
    <section className="section">
      <h3 className="section__title">时间线</h3>
      <dl className="kv">
        {TIMELINE.map(([key, label]) => (
          <div className="kv__row" key={key}>
            <dt className="kv__key">{label}</dt>
            <dd className="kv__value">{formatDateTime(data[key])}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function OrderItems({ data }: { data: JsonRecord }) {
  const items = Array.isArray(data.items) ? (data.items as JsonRecord[]) : []
  const itemsTotal = items.reduce(
    (sum, item) => sum + (typeof item.subtotal_cents === 'number' ? item.subtotal_cents : 0),
    0,
  )

  return (
    <section className="section">
      <h3 className="section__title">商品明细</h3>
      {items.length === 0 ? (
        <p className="muted">这个订单没有明细记录。</p>
      ) : (
        <>
          <DataTable rows={items} columns={ITEM_COLUMNS} />
          <p className="muted">
            明细合计 {formatCents(itemsTotal)}，订单实付 {formatCents(data.paid_amount_cents)}
          </p>
        </>
      )}
    </section>
  )
}

/** 订单详情（管理侧）—— GET /admin/orders/{order_no}，审批时核对退款依据用 */
export function AdminOrderDetailPage() {
  const { orderNo = '' } = useParams()

  return (
    <ResourceDetailPage
      title={`订单 ${orderNo}`}
      desc={
        <>
          来自 <code>GET /api/admin/orders/{orderNo}</code>，含商品明细与实付金额。
        </>
      }
      fetcher={() => fetchOrder(orderNo)}
      backTo="/admin/orders"
      backLabel="返回订单列表"
      omitKeys={['items', ...TIMELINE.map(([key]) => key)]}
      renderExtra={(data) => (
        <>
          <OrderTimeline data={data} />
          <OrderItems data={data} />
        </>
      )}
    />
  )
}
