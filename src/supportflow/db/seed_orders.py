"""创建本地演示订单与商品明细：python -m supportflow.db.seed_orders。

前提：先跑过 python -m supportflow.db.seed_users（订单按 username 找归属）。

两条硬约束，改数据时别破坏：
1. 可重复运行 —— 已存在的 order_no 直接跳过，不会出现第二份。
2. 时间字段一律相对当前 UTC 时间算出 —— 写死日期的话，过几天
   "签收 10 天"就变成"签收 15 天"，退款资格判定会自己翻面。
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from supportflow.db.base import utc_now
from supportflow.db.session import SessionLocal, engine
from supportflow.models import Order, OrderItem, User
from supportflow.models.enums import FulfillmentStatus, PaymentStatus


@dataclass(frozen=True)
class ItemSpec:
    """商品快照：下单时的名称、型号和单价，第一版不做商品管理。"""

    product_code: str
    product_name: str
    product_model: str | None
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class OrderSpec:
    order_no: str
    username: str
    paid_amount_cents: int
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    tracking_no: str | None
    # 相对天数；None 表示该时间点为空（未支付订单不应有发货/签收时间）。
    paid_days_ago: int | None
    shipped_days_ago: int | None
    delivered_days_ago: int | None
    items: tuple[ItemSpec, ...]


# 与 docs/acceptance-cases.md 的固定数据对齐：
# U1 = customer1 拥有 A1001~A1005，U2 = customer2 拥有 B1001。
# B1001 是归属检查的对照样本 —— 它必须始终属于另一个客户。
DEMO_ORDERS: tuple[OrderSpec, ...] = (
    OrderSpec(
        order_no="A1001",
        username="customer1",
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000001",
        paid_days_ago=12,
        shipped_days_ago=11,
        delivered_days_ago=10,
        # 两条明细合计 29900，与实付一致；顺带覆盖"一单多商品"。
        items=(
            ItemSpec("SKU-EP-100", "无线蓝牙耳机 Air", "EP-100", 1, 25900),
            ItemSpec("SKU-EP-101", "硅胶耳塞套（3 对）", "EP-101", 1, 4000),
        ),
    ),
    OrderSpec(
        order_no="A1002",
        username="customer1",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000002",
        paid_days_ago=17,
        shipped_days_ago=16,
        delivered_days_ago=15,
        items=(ItemSpec("SKU-SP-200", "桌面蓝牙音箱", "SP-200", 1, 19900),),
    ),
    OrderSpec(
        order_no="A1003",
        username="customer1",
        # 未支付订单实付为 0；明细照常记录商品原价快照。
        paid_amount_cents=0,
        payment_status=PaymentStatus.UNPAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        paid_days_ago=None,
        shipped_days_ago=None,
        delivered_days_ago=None,
        items=(ItemSpec("SKU-PB-300", "10000mAh 移动电源", "PB-300", 1, 12900),),
    ),
    OrderSpec(
        order_no="A1004",
        username="customer1",
        paid_amount_cents=8900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000004",
        paid_days_ago=22,
        shipped_days_ago=20,
        delivered_days_ago=18,
        items=(ItemSpec("SKU-CB-400", "Type-C 快充数据线 2m", "CB-400", 1, 8900),),
    ),
    OrderSpec(
        order_no="A1005",
        username="customer1",
        paid_amount_cents=45900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000005",
        paid_days_ago=6,
        shipped_days_ago=4,
        delivered_days_ago=3,
        items=(ItemSpec("SKU-EP-110", "头戴式降噪耳机", "EP-110", 1, 45900),),
    ),
    OrderSpec(
        order_no="B1001",
        username="customer2",
        paid_amount_cents=12900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000011",
        paid_days_ago=9,
        shipped_days_ago=8,
        delivered_days_ago=7,
        items=(ItemSpec("SKU-PB-310", "20000mAh 移动电源", "PB-310", 1, 12900),),
    ),
)


def _days_ago(now: datetime, days: int | None) -> datetime | None:
    """相对天数 → 绝对时间。数据库存 UTC 无时区时间，别在这里转时区。"""
    return None if days is None else now - timedelta(days=days)


def _check_amounts() -> None:
    """写库前自检：已支付订单的实付必须等于明细合计。

    数据库不校验这条一致性（金额只要求非负），写错了要到算退款金额时才发现。
    未支付订单实付为 0，明细是其原价快照，不参与比对。
    """
    for spec in DEMO_ORDERS:
        if spec.payment_status is PaymentStatus.UNPAID:
            continue
        items_total = sum(i.quantity * i.unit_price_cents for i in spec.items)
        if items_total != spec.paid_amount_cents:
            raise ValueError(
                f"{spec.order_no}: paid_amount_cents={spec.paid_amount_cents} "
                f"but items total {items_total}"
            )


async def main() -> None:
    _check_amounts()
    now = utc_now()
    created: list[OrderSpec] = []

    try:
        async with SessionLocal() as session:
            # 全部订单一起提交；中途失败时事务回滚，不会留下半份数据。
            async with session.begin():
                # 归属按 username 查，不写死自增 id —— 重建库后 id 会变。
                user_ids = dict(
                    (await session.execute(select(User.username, User.id))).all()
                )
                existing = set(await session.scalars(select(Order.order_no)))

                for spec in DEMO_ORDERS:
                    if spec.order_no in existing:
                        print(f"Skipped existing order: {spec.order_no}")
                        continue

                    user_id = user_ids.get(spec.username)
                    if user_id is None:
                        raise RuntimeError(
                            f"Missing demo account: {spec.username}; "
                            "run python -m supportflow.db.seed_users first"
                        )

                    order = Order(
                        order_no=spec.order_no,
                        user_id=user_id,
                        paid_amount_cents=spec.paid_amount_cents,
                        payment_status=spec.payment_status,
                        fulfillment_status=spec.fulfillment_status,
                        paid_at=_days_ago(now, spec.paid_days_ago),
                        shipped_at=_days_ago(now, spec.shipped_days_ago),
                        delivered_at=_days_ago(now, spec.delivered_days_ago),
                        tracking_no=spec.tracking_no,
                    )
                    session.add(order)
                    # flush 先写 orders 拿到自增 id，明细才能引用它（此时还没提交）。
                    await session.flush()

                    for item in spec.items:
                        session.add(OrderItem(order_id=order.id, **asdict(item)))

                    created.append(spec)

        total_items = sum(len(spec.items) for spec in created)
        print(f"Created {len(created)} order(s), {total_items} item(s).")
        for spec in created:
            print(
                f"order_no={spec.order_no} owner={spec.username} "
                f"paid_cents={spec.paid_amount_cents} "
                f"payment={spec.payment_status.value} "
                f"fulfillment={spec.fulfillment_status.value}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
