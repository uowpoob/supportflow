"""创建本地演示订单与商品明细：python -m supportflow.db.seed.seed_orders。

前提：先跑过 python -m supportflow.db.seed.seed_users（订单按 username 找归属）。

加 `--refresh` 会把**已存在**的订单覆盖回本文声明的状态与时间（新增的照常插入）——
点了半天演示之后想回到干净基线，跑这个参数即可，不用手工改库。

三条硬约束，改数据时别破坏：

1. 可重复运行 —— 已存在的 order_no 直接跳过（除非 `--refresh`），不会出现第二份。
2. 时间字段一律相对当前 UTC 时间算出 —— 写死日期的话，过几天
   "签收 10 天"就变成"签收 15 天"，退款资格判定会自己翻面。
3. **时间线必须因果成立**：下单 ≤ 支付 ≤ 发货 ≤ 签收，且都不晚于现在。
   早先的版本只填了 paid/shipped/delivered，`created_at` 由 ORM 默认写成插库时刻，
   于是库里出现"9 月 16 日下单、9 月 4 日支付"这种订单 —— 演示时一眼就被看出来。
   `_validate()` 会在写库前拦住这类数据（`anomaly=True` 的样本除外，见下表）。

时间都是相对"跑种子的那一刻"锚定的，所以整套数据会随时间漂移：越靠近 14 天窗口
边界的订单，越容易在几天后翻面（可退的变成超期）。演示或验收前重新跑一次
`seed_orders --refresh` 就能重新锚定，不用手工改库。
"""

import asyncio
import sys
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
    # 时间字段统一用"距今多久"，None 表示该时间点为空。
    # ⚠️ created_ago 必须**大于** paid_ago —— 先下单，后支付。
    created_ago: timedelta | None
    paid_ago: timedelta | None
    shipped_ago: timedelta | None
    delivered_ago: timedelta | None
    items: tuple[ItemSpec, ...]
    # 这单覆盖什么场景。不落库，只在跑完种子时打印出来，方便对着清单核对覆盖面。
    note: str = ""
    # 故意写坏的样本：跳过写库前的一致性自检，用来覆盖"数据异常 / 金额异常"分支。
    # 每一条都得在 note 里写清楚坏在哪，否则下一个人会以为是自己写错了。
    anomaly: bool = False


# 固定数据集：U1 = customer1 拥有 A 系列，U2 = customer2 拥有 B 系列。
#
# 覆盖面是刻意的，20 单正好把 `services/refunds.evaluate_eligibility` 的每个分支
# 都点亮一次（最后那个括号里是命中的 reason_code）：
#
#   ok ─────────────────── A1001 / A1005 / A1006 / A1012 / B1001 / B1004 / B1008
#   window_expired ─────── A1002（签收 15 天）、A1007（签收 14 天零 2 小时）
#   order_unpaid ───────── A1003 / B1006
#   order_refunded ─────── A1004
#   no_payable_amount ──── A1011（实付 0 但状态是已支付）
#   not_delivered ──────── A1008（未发货）、A1009（已发货未签收）、B1007（签收时间为空）
#   delivered_time_in_future ─ A1010（签收时间在未来）
#   already_requested ──── B1002 / B1003 / B1005（由 seed_refunds 建申请占位）
#
# 顺带覆盖的展示场景：一单多商品（A1001）、数量大于 1（A1012）、
# 大额订单 9596.00 元（A1012）、小额订单 39.00 元（B1006）、无运单号（A1003/A1008/B1006）。
#
# A1001 / A1002 / A1003 / A1004 / A1005 / B1001 是 docs/acceptance-cases.md 写死的
# 演示数据，**编号和含义不能改** —— 文档里的验收用例直接引用它们。
DEMO_ORDERS: tuple[OrderSpec, ...] = (
    # ---------------------------- customer1 ----------------------------
    OrderSpec(
        order_no="A1001",
        username="customer1",
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000001",
        created_ago=timedelta(days=13),
        paid_ago=timedelta(days=12),
        shipped_ago=timedelta(days=11),
        delivered_ago=timedelta(days=10),
        # 两条明细合计 29900，与实付一致；顺带覆盖"一单多商品"。
        items=(
            ItemSpec("SKU-EP-100", "无线蓝牙耳机 Air", "EP-100", 1, 25900),
            ItemSpec("SKU-EP-101", "硅胶耳塞套（3 对）", "EP-101", 1, 4000),
        ),
        note="基准可退单：签收 10 天，多商品",
    ),
    OrderSpec(
        order_no="A1002",
        username="customer1",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000002",
        created_ago=timedelta(days=18),
        paid_ago=timedelta(days=17),
        shipped_ago=timedelta(days=16),
        delivered_ago=timedelta(days=15),
        items=(ItemSpec("SKU-SP-200", "桌面蓝牙音箱", "SP-200", 1, 19900),),
        note="超期：签收 15 天，超出 14 天窗口",
    ),
    OrderSpec(
        order_no="A1003",
        username="customer1",
        # 未支付订单实付为 0；明细照常记录商品原价快照。
        paid_amount_cents=0,
        payment_status=PaymentStatus.UNPAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=2),
        paid_ago=None,
        shipped_ago=None,
        delivered_ago=None,
        items=(ItemSpec("SKU-PB-300", "10000mAh 移动电源", "PB-300", 1, 12900),),
        note="未支付：没有支付时间，不能申请退款",
    ),
    OrderSpec(
        order_no="A1004",
        username="customer1",
        paid_amount_cents=8900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000004",
        created_ago=timedelta(days=22),
        paid_ago=timedelta(days=21),
        shipped_ago=timedelta(days=20),
        delivered_ago=timedelta(days=18),
        items=(ItemSpec("SKU-CB-400", "Type-C 快充数据线 2m", "CB-400", 1, 8900),),
        note="已退款：完整退款链路（申请/审批/流水），永久不能重复申请",
    ),
    OrderSpec(
        order_no="A1005",
        username="customer1",
        paid_amount_cents=45900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000005",
        created_ago=timedelta(days=7),
        paid_ago=timedelta(days=6),
        shipped_ago=timedelta(days=4),
        delivered_ago=timedelta(days=3),
        items=(ItemSpec("SKU-EP-110", "头戴式降噪耳机", "EP-110", 1, 45900),),
        note="基准可退单：签收 3 天",
    ),
    OrderSpec(
        order_no="A1006",
        username="customer1",
        paid_amount_cents=32900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000006",
        created_ago=timedelta(days=16),
        paid_ago=timedelta(days=15),
        shipped_ago=timedelta(days=14),
        # ⚠️ 这里**不能**写"恰好 14 天"：时间是相对播种那一刻算出来的，
        # 秒针一走就变成 14 天零几秒，判定立刻翻面成超期。
        # 精确边界（14 天整允许、14 天零 1 微秒拒绝）由针对纯函数的单元测试覆盖，
        # 演示数据只负责"窗口快到期"这种稳定可观察的状态。
        delivered_ago=timedelta(days=13),
        items=(ItemSpec("SKU-KB-500", "机械键盘 87 键", "KB-500", 1, 32900),),
        note="窗口内靠后：签收 13 天，距退款截止只剩约 1 天",
    ),
    OrderSpec(
        order_no="A1007",
        username="customer1",
        paid_amount_cents=15900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000007",
        created_ago=timedelta(days=17),
        paid_ago=timedelta(days=16),
        shipped_ago=timedelta(days=15),
        # 窗口关闭 2 小时 —— 和 A1006 配对：一个还在窗口内、一个刚出窗口。
        delivered_ago=timedelta(days=14, hours=2),
        items=(ItemSpec("SKU-MS-600", "无线鼠标 静音版", "MS-600", 1, 15900),),
        note="刚过窗口：签收 14 天零 2 小时，退款窗口已关闭",
    ),
    OrderSpec(
        order_no="A1008",
        username="customer1",
        paid_amount_cents=129900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=3),
        paid_ago=timedelta(days=2),
        shipped_ago=None,
        delivered_ago=None,
        items=(ItemSpec("SKU-MN-700", "27 英寸 2K 显示器", "MN-700", 1, 129900),),
        note="已支付未发货：付款了但还没签收",
    ),
    OrderSpec(
        order_no="A1009",
        username="customer1",
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.SHIPPED,
        tracking_no="SF1000000009",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=1),
        delivered_ago=None,
        items=(ItemSpec("SKU-CM-800", "4K 高清摄像头", "CM-800", 1, 29900),),
        note="已发货未签收：在途，签收后才开始算 14 天",
    ),
    OrderSpec(
        order_no="A1010",
        username="customer1",
        paid_amount_cents=24900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000010",
        created_ago=timedelta(days=1),
        paid_ago=timedelta(hours=12),
        shipped_ago=timedelta(hours=6),
        # 负值 = 未来的时间。这单是**故意写坏**的：签收时间不可能晚于现在。
        delivered_ago=timedelta(days=-1),
        items=(ItemSpec("SKU-RT-900", "千兆无线路由器", "RT-900", 1, 24900),),
        note="数据异常（故意）：签收时间在未来 → delivered_time_in_future",
        anomaly=True,
    ),
    OrderSpec(
        order_no="A1011",
        username="customer1",
        # 状态说已支付、实付却是 0 —— 同样是**故意写坏**的：正常支付流程不会产生这种订单。
        paid_amount_cents=0,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000011",
        created_ago=timedelta(days=8),
        paid_ago=timedelta(days=7),
        shipped_ago=timedelta(days=6),
        delivered_ago=timedelta(days=5),
        items=(ItemSpec("SKU-CS-110", "手机保护壳", "CS-110", 1, 5900),),
        note="数据异常（故意）：已支付但实付 0 → no_payable_amount",
        anomaly=True,
    ),
    OrderSpec(
        order_no="A1012",
        username="customer1",
        # 三行明细：8999.00 + 399.00 + 99.00×2 = 9596.00。
        paid_amount_cents=959600,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF1000000012",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=2),
        delivered_ago=timedelta(days=1),
        items=(
            ItemSpec("SKU-NB-120", "轻薄笔记本 14 英寸", "NB-120", 1, 899900),
            ItemSpec("SKU-DK-121", "雷电扩展坞", "DK-121", 1, 39900),
            ItemSpec("SKU-CB-122", "Type-C 转接线 0.5m", "CB-122", 2, 9900),
        ),
        note="大额 + 数量大于 1：实付 9596.00 元，签收 1 天",
    ),
    # ---------------------------- customer2 ----------------------------
    OrderSpec(
        order_no="B1001",
        username="customer2",
        paid_amount_cents=12900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000001",
        created_ago=timedelta(days=10),
        paid_ago=timedelta(days=9),
        shipped_ago=timedelta(days=8),
        delivered_ago=timedelta(days=7),
        items=(ItemSpec("SKU-PB-310", "20000mAh 移动电源", "PB-310", 1, 12900),),
        note="归属对照样本：必须始终属于 customer2，且本身可退",
    ),
    OrderSpec(
        order_no="B1002",
        username="customer2",
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000002",
        created_ago=timedelta(days=5),
        paid_ago=timedelta(days=4),
        shipped_ago=timedelta(days=3),
        delivered_ago=timedelta(days=2),
        items=(ItemSpec("SKU-SP-210", "便携蓝牙音箱", "SP-210", 1, 29900),),
        note="已有待审批申请（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="B1003",
        username="customer2",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000003",
        created_ago=timedelta(days=8),
        paid_ago=timedelta(days=7),
        shipped_ago=timedelta(days=6),
        delivered_ago=timedelta(days=4),
        items=(ItemSpec("SKU-ST-220", "平板电脑支架 铝合金", "ST-220", 1, 19900),),
        note="已有已批准申请 + 退款执行中（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="B1004",
        username="customer2",
        paid_amount_cents=6900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000004",
        created_ago=timedelta(days=12),
        paid_ago=timedelta(days=11),
        shipped_ago=timedelta(days=10),
        delivered_ago=timedelta(days=6),
        items=(ItemSpec("SKU-WR-230", "键盘腕托 记忆棉", "WR-230", 1, 6900),),
        note="曾被拒绝（seed_refunds 建）→ 名额已释放，**这单仍然可退**",
    ),
    OrderSpec(
        order_no="B1005",
        username="customer2",
        paid_amount_cents=9900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000005",
        created_ago=timedelta(days=13),
        paid_ago=timedelta(days=12),
        shipped_ago=timedelta(days=11),
        delivered_ago=timedelta(days=9),
        items=(ItemSpec("SKU-CM-240", "车载手机支架", "CM-240", 1, 9900),),
        note="已批准但打款失败（seed_refunds 建失败流水）→ already_requested",
    ),
    OrderSpec(
        order_no="B1006",
        username="customer2",
        paid_amount_cents=0,
        payment_status=PaymentStatus.UNPAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=5),
        paid_ago=None,
        shipped_ago=None,
        delivered_ago=None,
        items=(ItemSpec("SKU-CS-250", "液态硅胶手机壳", "CS-250", 1, 3900),),
        note="未支付：小额单（39.00 元），customer2 视角",
    ),
    OrderSpec(
        order_no="B1007",
        username="customer2",
        paid_amount_cents=11900,
        payment_status=PaymentStatus.PAID,
        # 状态说已签收、时间却为空 —— **故意写坏**的数据不完整样本。
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000007",
        created_ago=timedelta(days=6),
        paid_ago=timedelta(days=5),
        shipped_ago=timedelta(days=4),
        delivered_ago=None,
        items=(ItemSpec("SKU-AC-260", "65W 氮化镓充电器", "AC-260", 1, 11900),),
        note="数据不完整（故意）：状态已签收但没有签收时间 → not_delivered",
        anomaly=True,
    ),
    OrderSpec(
        order_no="B1008",
        username="customer2",
        paid_amount_cents=129900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF2000000008",
        created_ago=timedelta(days=3),
        paid_ago=timedelta(days=2),
        shipped_ago=timedelta(days=1),
        # 6 小时前刚签收：窗口的**第一天**，也是可退的。
        delivered_ago=timedelta(hours=6),
        items=(ItemSpec("SKU-WT-270", "智能运动手表", "WT-270", 1, 129900),),
        note="窗口起点：6 小时前刚签收，可退",
    ),
)


def _at(now: datetime, ago: timedelta | None) -> datetime | None:
    """相对偏移 → 绝对时间。数据库存 UTC 无时区时间，别在这里转时区。"""
    return None if ago is None else now - ago


def _validate() -> None:
    """写库前自检：编号不重复、金额对得上、时间线因果成立、状态与时间不打架。

    这四类错误数据库一条都不管（金额只要非负，时间字段之间毫无约束），
    但每一条都会毁掉演示：最容易露馅的就是"下单时间晚于支付时间"。
    与其等别人看库时发现，不如在这里直接起不来。
    `anomaly=True` 的样本跳过 —— 它们存在的意义就是被判定逻辑拒绝。
    """
    seen: set[str] = set()

    for spec in DEMO_ORDERS:
        if spec.order_no in seen:
            raise ValueError(f"订单号重复：{spec.order_no}")
        seen.add(spec.order_no)

        if spec.anomaly:
            continue

        if spec.created_ago is None:
            raise ValueError(f"{spec.order_no}: created_ago 必填，订单不可能没有下单时间")

        # 已支付 / 已退款订单的实付必须等于明细合计。
        # 未支付订单实付为 0，明细是其原价快照，不参与比对。
        if spec.payment_status is not PaymentStatus.UNPAID:
            items_total = sum(i.quantity * i.unit_price_cents for i in spec.items)
            if items_total != spec.paid_amount_cents:
                raise ValueError(
                    f"{spec.order_no}: paid_amount_cents={spec.paid_amount_cents} "
                    f"but items total {items_total}"
                )

        if spec.paid_ago is None and spec.payment_status is not PaymentStatus.UNPAID:
            raise ValueError(f"{spec.order_no}: 状态是 {spec.payment_status}，必须有支付时间")

        if spec.delivered_ago is None and spec.fulfillment_status is FulfillmentStatus.DELIVERED:
            raise ValueError(f"{spec.order_no}: 状态已签收，必须有签收时间")

        # 时间线：越靠后的环节，距今越近。换算成"多久以前"就是**单调不增**。
        # 写成"必须严格递减"会误伤同一秒内完成的动作（比如刚下单就支付）。
        previous_name: str | None = None
        previous_ago: timedelta | None = None
        for name, ago in (
            ("created_at", spec.created_ago),
            ("paid_at", spec.paid_ago),
            ("shipped_at", spec.shipped_ago),
            ("delivered_at", spec.delivered_ago),
        ):
            if ago is None:
                continue
            if ago < timedelta(0):
                raise ValueError(f"{spec.order_no}: {name} 落在未来，时间线不成立")
            if previous_ago is not None and ago > previous_ago:
                raise ValueError(
                    f"{spec.order_no}: {name} 早于 {previous_name}，"
                    "应满足「下单 ≤ 支付 ≤ 发货 ≤ 签收」"
                )
            previous_name, previous_ago = name, ago


def _apply(order: Order, spec: OrderSpec, user_id: int, now: datetime) -> None:
    """把一条声明写进 ORM 对象。

    新增和刷新共用这一份 —— 两条路径若各写一遍，迟早出现"新建的订单时间对、
    刷新的订单时间错"这种只在一半场景里复现的问题。
    """
    created_at = _at(now, spec.created_ago)
    paid_at = _at(now, spec.paid_ago)
    shipped_at = _at(now, spec.shipped_ago)
    delivered_at = _at(now, spec.delivered_ago)

    order.order_no = spec.order_no
    order.user_id = user_id
    order.paid_amount_cents = spec.paid_amount_cents
    order.payment_status = spec.payment_status
    order.fulfillment_status = spec.fulfillment_status
    order.tracking_no = spec.tracking_no
    order.paid_at = paid_at
    order.shipped_at = shipped_at
    order.delivered_at = delivered_at

    # created_at 必须显式写：ORM 默认值是 utc_now()，不写就会变成"今天下单"。
    order.created_at = created_at
    # updated_at 取"最后一个已经发生过的动作"。
    # 对 A1010 那种签收时间在未来的异常样本，用 min 压回现在，
    # 免得库里出现一条 updated_at 也在未来的记录。
    events = [t for t in (created_at, paid_at, shipped_at, delivered_at) if t is not None]
    order.updated_at = min(max(events), now)


async def main(refresh: bool = False) -> None:
    _validate()
    now = utc_now()
    created: list[OrderSpec] = []
    refreshed: list[OrderSpec] = []
    skipped: list[OrderSpec] = []

    try:
        async with SessionLocal() as session:
            # 全部订单一起提交；中途失败时事务回滚，不会留下半份数据。
            async with session.begin():
                # 归属按 username 查，不写死自增 id —— 重建库后 id 会变。
                user_ids = dict(
                    (await session.execute(select(User.username, User.id))).all()
                )
                existing = {
                    order.order_no: order
                    for order in await session.scalars(
                        select(Order).where(
                            Order.order_no.in_([spec.order_no for spec in DEMO_ORDERS])
                        )
                    )
                }

                for spec in DEMO_ORDERS:
                    user_id = user_ids.get(spec.username)
                    if user_id is None:
                        raise RuntimeError(
                            f"Missing demo account: {spec.username}; "
                            "run python -m supportflow.db.seed.seed_users first"
                        )

                    if spec.order_no in existing:
                        if not refresh:
                            skipped.append(spec)
                            continue
                        _apply(existing[spec.order_no], spec, user_id, now)
                        refreshed.append(spec)
                        continue

                    order = Order(order_no=spec.order_no)
                    _apply(order, spec, user_id, now)
                    session.add(order)
                    # flush 先写 orders 拿到自增 id，明细才能引用它（此时还没提交）。
                    await session.flush()

                    for item in spec.items:
                        session.add(OrderItem(order_id=order.id, **asdict(item)))

                    created.append(spec)

        total_items = sum(len(spec.items) for spec in created)
        print(
            f"Orders: created {len(created)}, refreshed {len(refreshed)}, "
            f"skipped {len(skipped)}; {total_items} item(s) inserted."
        )
        if skipped and not refresh:
            print("（想把这些订单覆盖回声明状态，加 --refresh 重跑）")
        # 打印覆盖清单：种子跑完直接对着它核对"该覆盖的场景是不是都在"。
        for spec in (*created, *refreshed):
            print(
                f"  order_no={spec.order_no} owner={spec.username} "
                f"paid_cents={spec.paid_amount_cents} "
                f"payment={spec.payment_status.value} "
                f"fulfillment={spec.fulfillment_status.value} "
                f"| {spec.note}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(refresh="--refresh" in sys.argv[1:]))
