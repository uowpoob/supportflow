"""订单查询接口的响应结构（只描述"给出去什么"）。

分层思路：**界面需要什么形状，就定义什么对象**，不要让 ORM 实体直接出境。
理由是 ORM 对象带着全部字段和它们之间的加载关系，一旦直接序列化：
一是会把 user_id、内部主键这类字段顺带泄露出去，二是以后加一列就自动改了接口。

三个对象各有明确的分工：
- `OrderItemOut`：单条商品明细，只出现在详情里
- `OrderBrief`：列表行 —— **故意不带明细**，列表不需要，带上就是每单多查一次
- `OrderDetail`：详情 = 列表行 + 时间字段 + 明细
再套一个 `OrderPage` 承载分页，它才是塞进 `Success.data` 的那个。
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

from supportflow.models.entities import Order, OrderItem
from supportflow.models.enums import FulfillmentStatus, PaymentStatus


def _iso_utc(value: datetime) -> str:
    """UTC 无时区时间 → 带 Z 的 ISO 字符串。

    两个都不能省：
    1. **必须带 Z**：数据库里存的是 UTC（`utc_now()` 摘掉了 tzinfo），直接序列化
       会得到 `"2026-09-16T10:53:00"` 这种不带时区的串，浏览器按本地时区解析 → 差 8 小时。
    2. **小数秒截到毫秒**：数据库精度是微秒（`DATETIME(6)`），原样输出是 6 位小数秒。
       ECMAScript 的日期格式只认 3 位，V8 会宽容地截断，**Safari 直接返回 Invalid Date**。
       前端虽然有兜底（解析失败就显示原文），但没理由让它去走那条路。
    """
    return (
        value.replace(tzinfo=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _iso_utc_or_null(value: datetime | None) -> str | None:
    return None if value is None else _iso_utc(value)


UtcInstant = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]
UtcInstantOrNull = Annotated[
    datetime | None, PlainSerializer(_iso_utc_or_null, return_type=str | None)
]


class OrderItemOut(BaseModel):
    """订单明细：下单时的商品快照。"""

    id: int
    product_code: str
    product_name: str
    product_model: str | None
    quantity: int
    unit_price_cents: int
    subtotal_cents: int = Field(description="quantity × unit_price_cents，由服务端算好")

    @classmethod
    def from_row(cls, item: OrderItem) -> "OrderItemOut":
        return cls(
            id=item.id,
            product_code=item.product_code,
            product_name=item.product_name,
            product_model=item.product_model,
            quantity=item.quantity,
            unit_price_cents=item.unit_price_cents,
            subtotal_cents=item.quantity * item.unit_price_cents,
        )


class OrderBrief(BaseModel):
    """列表行：够看就够了，不带明细。

    `username` 来自 `users` 表，不是订单自己的字段 —— 管理员要一眼看出
    这单是谁的，只给 `user_id` 等于让他自己去对账号表。
    """

    order_no: str
    user_id: int
    username: str
    paid_amount_cents: int
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    created_at: UtcInstant

    @classmethod
    def from_row(cls, order: Order, username: str) -> "OrderBrief":
        return cls(
            order_no=order.order_no,
            user_id=order.user_id,
            username=username,
            paid_amount_cents=order.paid_amount_cents,
            payment_status=order.payment_status,
            fulfillment_status=order.fulfillment_status,
            created_at=order.created_at,
        )


class OrderDetail(OrderBrief):
    """订单详情 = 列表行的字段 + 履约时间线 + 商品明细。"""

    paid_at: UtcInstantOrNull
    shipped_at: UtcInstantOrNull
    delivered_at: UtcInstantOrNull
    tracking_no: str | None
    items: list[OrderItemOut]

    @classmethod
    def from_row(
        cls, order: Order, username: str, items: list[OrderItem]
    ) -> "OrderDetail":
        return cls(
            order_no=order.order_no,
            user_id=order.user_id,
            username=username,
            paid_amount_cents=order.paid_amount_cents,
            payment_status=order.payment_status,
            fulfillment_status=order.fulfillment_status,
            created_at=order.created_at,
            paid_at=order.paid_at,
            shipped_at=order.shipped_at,
            delivered_at=order.delivered_at,
            tracking_no=order.tracking_no,
            items=[OrderItemOut.from_row(item) for item in items],
        )


class OrderPage(BaseModel):
    """分页信封，最终塞进 `Success.data`。

    `items` / `total` 这两个字段名是**前后端约定**，不是随便起的：
    前端 `web/src/api/list.ts::normalizeList` 就是按这两个名字认列表的，改名要一起改。
    """

    items: list[OrderBrief]
    total: int = Field(description="满足条件的总行数，与当前页无关")
    offset: int
    limit: int
