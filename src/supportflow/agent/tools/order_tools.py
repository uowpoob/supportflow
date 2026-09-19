"""订单相关的 Agent 工具。
`user_id` 不出现在任何一个工具的签名里 —— 它由 `build_order_tools` 用闭包钉死。
模型只能决定"查哪个订单号"，永远决定不了"查谁的数据"。
"""

from datetime import datetime

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.enums import FulfillmentStatus, PaymentStatus
from supportflow.services import orders as order_service
from supportflow.services import refunds as refund_service


_PAYMENT_CN = {
    PaymentStatus.UNPAID: "未支付",
    PaymentStatus.PAID: "已支付",
    PaymentStatus.REFUNDED: "已退款",
}
_FULFILLMENT_CN = {
    FulfillmentStatus.UNSHIPPED: "未发货",
    FulfillmentStatus.SHIPPED: "已发货",
    FulfillmentStatus.DELIVERED: "已签收",
}

_LIST_LIMIT=10



def _fmt(moment: datetime | None) -> str:
    """库里存的是 UTC 无时区时间（见 `db/base.py` 的 `utc_now`）。

    格式化时补上 UTC 标记 —— 否则模型会把它当成本地时间讲给客户，差 8 小时。
    """
    return "未记录" if moment is None else moment.strftime("%Y-%m-%d %H:%M UTC")


def _one_line(order) -> str:
    return (
        f"- {order.order_no}｜下单 {_fmt(order.created_at)}"
        f"｜支付 {_PAYMENT_CN[order.payment_status]}"
        f"｜履约 {_FULFILLMENT_CN[order.fulfillment_status]}"
        f"｜实付 {order.paid_amount_cents} 分"
    )


def build_order_tools(db: AsyncSession, user_id: int) -> list:
    @tool
    async def get_order_detail(order_no: str) -> str:
        """当用户想知道某个订单的状态、金额或签收时间时调用。
        order_no 是订单号，形如 A1001，不是用户 ID。"""
        order = await order_service.get_order_for_user(db, user_id, order_no)
        if order is None:
            return f"没有找到订单 {order_no}。"
        return "\n".join(
            [
                _one_line(order),
                f"- 支付时间 {_fmt(order.paid_at)}｜发货时间 {_fmt(order.shipped_at)}"
                f"｜签收时间 {_fmt(order.delivered_at)}",
            ]
        )

    @tool
    async def list_my_orders() -> str:
        """当用户想知道自己有哪些订单时调用，比如"我都有啥订单""我买了什么"
        "我的订单列表"。不需要任何参数 —— 只会返回当前登录用户自己的订单，
        不含其他客户的数据。"""
        orders, total = await order_service.list_orders_for_user(
            db, user_id, offset=0, limit=_LIST_LIMIT
        )
        if not orders:
            return "你名下还没有任何订单。"

        lines = [f"你共有 {total} 笔订单，按时间从新到旧：", ""]
        lines += [_one_line(order) for order in orders]
        if total > len(orders):
            lines.append(f"（只列出最近 {len(orders)} 笔）")
        return "\n".join(lines)

    @tool
    async def get_refund_eligibility(order_no: str) -> str:
        """当用户问某笔订单"能不能退款""还能退吗""退款截止到几号"时调用。
        order_no 是订单号，形如 A1001，不是用户 ID。只看资格，不会真的提交申请。"""
        found = await refund_service.check_refund_eligibility(db, user_id, order_no)
        if found is None:
            return f"没有找到订单 {order_no}。"

        _, eligibility = found
        head = "可以申请退款" if eligibility.eligible else "不能申请退款"
        lines = [f"- 订单 {order_no}：{head}｜{eligibility.message}"]
        if eligibility.eligible:
            lines.append(f"- 可退金额 {eligibility.amount_cents} 分")
        if eligibility.delivered_at is not None:
            lines.append(f"- 签收时间 {_fmt(eligibility.delivered_at)}")
        if eligibility.window_ends_at is not None:
            lines.append(f"- 退款期限截止 {_fmt(eligibility.window_ends_at)}")
        if eligibility.existing_request_key is not None:
            lines.append(f"- 已有一条退款申请 {eligibility.existing_request_key}")
        return "\n".join(lines)


    @tool
    async def get_order_item(order_no: str) -> str:
        """
        当用户询问有关商品信息时调用，如果用户未指明提供订单号就从所有订单号中挨个查询，所有订单
        order_no是订单号 ，查询后解析返回的商品名和型号判断是否是用户询问的商品，可能查询到多个商品信息，如果有询问用户具体指哪一个，
        如果用户说不是这个的话 说明在调用查询订单信息的方法中最大查询的数目不包括用户所指定的商品订单，那么再次调用查询订单工具，此时offset要等于limit
        """
        found = await order_service.get_order_with_items_for_user(db, user_id, order_no)
        if found is None:
            return "订单不存在"
        order, items = found
        lines = ["是如下商品吗"]
        for item in items:

            lines.append(f"商品名{item.product_name}")
            lines.append(f"商品型号{item.product_model}")
            lines.append(f"商品价格{item.unit_price_cents}")
            lines.append(f"商品数量{item.quantity}")
        return "\n".join(lines)


    return [get_order_detail, list_my_orders, get_refund_eligibility, get_order_item]

