"""小米演示订单：两位客户各 20 单，金额为模拟成交价，不代表官网售价。

订单号稳定，所有时间相对同一次播种的 UTC 时间锚定。
覆盖未支付、待发货、运输中、签收、超期、退款，以及多商品和多件数量。
完整刷新请运行 python -m supportflow.db.seed.seed_demo --refresh，
在同一个事务内同步更新订单、商品明细、退款申请、审批与流水。
"""

import asyncio
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.db.session import SessionLocal, engine
from supportflow.models import Order, OrderItem, User
from supportflow.models.enums import FulfillmentStatus, PaymentStatus


@dataclass(frozen=True)
class Product:
    """下单时的商品快照来源，第一版不做商品管理。"""

    product_code: str
    product_name: str
    product_model: str
    unit_price_cents: int


@dataclass(frozen=True)
class ItemSpec:
    """订单里的一行明细。quantity 默认 1。"""

    product_code: str
    product_name: str
    product_model: str
    quantity: int
    unit_price_cents: int


# 演示用商品目录。key 是短别名，只在本文件里用。
CATALOG: dict[str, Product] = {
    "xiaomi14ultra": Product("SKU-MI-14U-512", "小米 14 Ultra", "16GB+512GB 黑色", 649900),
    "xiaomi14case": Product("SKU-MI-14-CASE", "小米 14 硅胶保护壳", "黑色", 9900),
    "xiaomibuds4pro": Product("SKU-MI-BUDS4-PRO", "小米 Buds 4 Pro", "星耀金", 99900),
    "redmibuds5pro": Product("SKU-MI-RBUDS5-PRO", "REDMI Buds 5 Pro", "曜石黑", 39900),
    "xiaomibluetooth": Product("SKU-MI-SPK", "小米 蓝牙音箱", "黑色", 19900),
    "mispkplay": Product("SKU-MI-SPK-PLAY", "小米 蓝牙音箱 Play", "黑色", 12900),
    "mipb20": Product("SKU-MI-PB20", "小米 移动电源", "20000mAh 22.5W", 12900),
    "mipb10": Product("SKU-MI-PB10", "小米 移动电源", "10000mAh 22.5W", 9900),
    "xiaomigan65w": Product("SKU-MI-GAN65", "小米 氮化镓充电器", "65W Type-C", 14900),
    "xiaomicharger33w": Product("SKU-MI-CHG33", "小米 充电器", "33W Type-C", 6900),
    "xiaomicable": Product("SKU-MI-CABLE-C", "小米 USB-C 数据线", "1m 白色", 2900),
    "xiaomicable6a": Product("SKU-MI-CABLE-6A", "小米 USB-C 数据线", "6A 1m 白色", 3900),
    "redmibookpro16": Product("SKU-MI-RBOOK-PRO16", "REDMI Book Pro 16", "16GB+1TB 灰色", 599900),
    "redmibook14": Product("SKU-MI-RBOOK14", "REDMI Book 14", "16GB+512GB 灰色", 449900),
    "xiaomipad6": Product("SKU-MI-PAD6", "小米 平板 6", "8GB+256GB 引力灰", 189900),
    "xiaomiusbhub": Product("SKU-MI-USB-HUB", "小米 USB 分线器", "四口 白色", 9900),
    "mijiaairpurifier4": Product("SKU-MI-AIR4", "米家 空气净化器 4", "白色", 89900),
    "xiaomikeyboard": Product("SKU-MI-KB", "小米 无线键盘", "黑色", 12900),
    "xiaomimouse": Product("SKU-MI-MOUSE", "小米 无线鼠标", "黑色", 6900),
    "mijiacamera3": Product("SKU-MI-CAM3", "小米 智能摄像机 3 云台版", "白色", 19900),
    "mijiasensor": Product("SKU-MI-TEMP2", "米家 蓝牙温湿度计 2", "白色", 6900),
    "redmimonitor27": Product("SKU-MI-RMON27", "REDMI 显示器", "27英寸 2K 黑色", 99900),
    "xiaomiwatchs3": Product("SKU-MI-WATCH-S3", "小米 Watch S3", "黑色", 79900),
    "xiaomiband9": Product("SKU-MI-BAND9", "小米 手环 9", "午夜黑", 24900),
    "xiaomirouterax3000": Product("SKU-MI-AX3000", "小米 路由器 AX3000", "黑色", 29900),
    "mics250": Product("SKU-MI-CS14", "小米 液态硅胶手机壳", "小米 14 款 白色", 3900),
    "xiaomicarcharger": Product("SKU-MI-CAR-WC", "小米 无线车充", "20W 黑色", 19900),
    "robot1s": Product("SKU-MI-ROBOT1S", "米家 全能扫拖机器人 1S", "白色", 299900),
    "washer12": Product("SKU-MI-WASH12", "米家 洗衣机", "XHQG120MJ103 白色", 249900),
    "circulationfan": Product("SKU-MI-FAN", "米家 智能直流变频循环扇", "落地式 白色", 34900),
    "waterboiler5l": Product("SKU-MI-BOILER5", "米家 智能电热水瓶", "5L 白色", 29900),
    "carhumidifier": Product("SKU-MI-CAR-HUM", "米家 智能车载加湿器", "黑色", 9900),
    "airfryer65l": Product("SKU-MI-AIRFRY65", "米家 智能空气炸锅 Pro 蒸烤版", "6.5L 白色", 59900),
    "airconditioner": Product("SKU-MI-AC", "米家 空调", "1.5匹 白色", 219900),
}


def item(alias: str, quantity: int = 1) -> ItemSpec:
    """从目录取一行明细。商品名/型号/单价都只有一个来源，不可能抄歪。"""
    product = CATALOG[alias]
    return ItemSpec(
        product_code=product.product_code,
        product_name=product.product_name,
        product_model=product.product_model,
        quantity=quantity,
        unit_price_cents=product.unit_price_cents,
    )


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
    # 人看的短名（C1-01），只用于注释、文档和打印，不落库。
    label: str = ""
    # 这单覆盖什么场景。不落库，只在跑完种子时打印出来，方便对着清单核对覆盖面。
    note: str = ""


DEMO_ORDERS: tuple[OrderSpec, ...] = (
    OrderSpec(
        order_no="1260918430020001",
        label="C1-01",
        username="customer1",
        paid_amount_cents=649900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467219",
        created_ago=timedelta(days=13),
        paid_ago=timedelta(days=12),
        shipped_ago=timedelta(days=11),
        delivered_ago=timedelta(days=10),
        items=(item("xiaomi14ultra"),),
        note="基准可退单：签收 10 天；大额 6499.00 元",
    ),
    OrderSpec(
        order_no="1260918430020002",
        label="C1-02",
        username="customer1",
        paid_amount_cents=99900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467220",
        created_ago=timedelta(days=18),
        paid_ago=timedelta(days=17),
        shipped_ago=timedelta(days=16),
        delivered_ago=timedelta(days=15),
        items=(item("xiaomibuds4pro"),),
        note="超期：签收 15 天，超出 14 天窗口",
    ),
    OrderSpec(
        order_no="1260918430020003",
        label="C1-03",
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
        items=(item("mipb20"),),
        note="未支付：没有支付时间，不能申请退款",
    ),
    OrderSpec(
        order_no="1260918430020004",
        label="C1-04",
        username="customer1",
        paid_amount_cents=2900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467222",
        created_ago=timedelta(days=22),
        paid_ago=timedelta(days=21),
        shipped_ago=timedelta(days=20),
        delivered_ago=timedelta(days=18),
        items=(item("xiaomicable"),),
        note="已退款：完整退款链路（申请/审批/流水），永久不能重复申请",
    ),
    OrderSpec(
        order_no="1260918430020005",
        label="C1-05",
        username="customer1",
        paid_amount_cents=39900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467223",
        created_ago=timedelta(days=7),
        paid_ago=timedelta(days=6),
        shipped_ago=timedelta(days=4),
        delivered_ago=timedelta(days=3),
        items=(item("redmibuds5pro"),),
        note="基准可退单：签收 3 天，真无线降噪耳机",
    ),
    OrderSpec(
        order_no="1260918430020006",
        label="C1-06",
        username="customer1",
        paid_amount_cents=12900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467224",
        created_ago=timedelta(days=16),
        paid_ago=timedelta(days=15),
        shipped_ago=timedelta(days=14),
        # 不能写"恰好 14 天"：时间相对播种时刻算，秒针一走就翻面成超期；
        # 精确边界由纯函数单测覆盖，演示数据只负责"窗口快到期"的稳定状态。
        delivered_ago=timedelta(days=13),
        items=(item("xiaomikeyboard"),),
        note="窗口内靠后：签收 13 天，距退款截止只剩约 1 天",
    ),
    OrderSpec(
        order_no="1260918430020007",
        label="C1-07",
        username="customer1",
        paid_amount_cents=6900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467225",
        created_ago=timedelta(days=17),
        paid_ago=timedelta(days=16),
        shipped_ago=timedelta(days=15),
        # 窗口关闭 2 小时 —— 和 C1-06 配对：一个还在窗口内、一个刚出窗口。
        delivered_ago=timedelta(days=14, hours=2),
        items=(item("xiaomimouse"),),
        note="刚过窗口：签收 14 天零 2 小时，退款窗口已关闭",
    ),
    OrderSpec(
        order_no="1260918430020008",
        label="C1-08",
        username="customer1",
        paid_amount_cents=599900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=3),
        paid_ago=timedelta(days=2),
        shipped_ago=None,
        delivered_ago=None,
        items=(item("redmibookpro16"),),
        note="已支付未发货：大额笔记本，付款了但还没签收",
    ),
    OrderSpec(
        order_no="1260918430020009",
        label="C1-09",
        username="customer1",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.SHIPPED,
        tracking_no="SF150238467227",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=1),
        delivered_ago=None,
        items=(item("mijiacamera3"),),
        note="已发货未签收：在途，签收后才开始算 14 天",
    ),
    OrderSpec(
        order_no="1260918430020010",
        label="C1-10",
        username="customer1",
        paid_amount_cents=13800,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467228",
        created_ago=timedelta(days=9),
        paid_ago=timedelta(days=8),
        shipped_ago=timedelta(days=7),
        delivered_ago=timedelta(days=6),
        items=(item("xiaomicharger33w", quantity=2),),
        note="数量大于 1：同一商品买了两件，签收 6 天",
    ),
    OrderSpec(
        order_no="1260918430020011",
        label="C1-11",
        username="customer1",
        paid_amount_cents=99900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467229",
        created_ago=timedelta(days=11),
        paid_ago=timedelta(days=10),
        shipped_ago=timedelta(days=9),
        delivered_ago=timedelta(days=8),
        items=(item("redmimonitor27"),),
        note="已有已批准申请 + 退款打款中（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="1260918430020012",
        label="C1-12",
        username="customer1",
        paid_amount_cents=79900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467230",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=2),
        delivered_ago=timedelta(days=1),
        items=(item("xiaomiwatchs3"),),
        note="曾被拒绝（seed_refunds 建）→ 名额已释放，**这单仍然可退**",
    ),
    OrderSpec(
        order_no="1260918430020013",
        label="C1-13",
        username="customer1",
        paid_amount_cents=9900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467231",
        created_ago=timedelta(days=20),
        paid_ago=timedelta(days=19),
        shipped_ago=timedelta(days=18),
        delivered_ago=timedelta(days=16),
        items=(item("xiaomi14case"),),
        note="超期（小额）：签收 16 天，手机壳这类低价配件也走同一套规则",
    ),
    OrderSpec(
        order_no="1260918430020014",
        label="C1-14",
        username="customer1",
        paid_amount_cents=449900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467232",
        created_ago=timedelta(days=26),
        paid_ago=timedelta(days=25),
        shipped_ago=timedelta(days=24),
        delivered_ago=timedelta(days=22),
        items=(item("redmibook14"),),
        note="已退款（大额笔记本）：第二条完整退款链路",
    ),
    OrderSpec(
        order_no="1260918430020015",
        label="C1-15",
        username="customer1",
        paid_amount_cents=14900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467233",
        created_ago=timedelta(days=5),
        paid_ago=timedelta(days=4),
        shipped_ago=timedelta(days=3),
        delivered_ago=timedelta(days=2),
        items=(item("xiaomigan65w"),),
        note="已有待审批申请（seed_refunds 建）→ 管理侧待办里能批到这条",
    ),
    OrderSpec(
        order_no="1260918430020016",
        label="C1-16",
        username="customer1",
        paid_amount_cents=24600,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467234",
        created_ago=timedelta(days=6),
        paid_ago=timedelta(days=5),
        shipped_ago=timedelta(days=4),
        delivered_ago=timedelta(days=2),
        items=(
            item("xiaomiusbhub"),
            item("xiaomicable6a", quantity=2),
            item("mijiasensor"),
        ),
        note="一单多商品（三行）+ 数量大于 1：签收 2 天，合计 246.00 元",
    ),
    OrderSpec(
        order_no="1270189029630001",
        label="C2-01",
        username="customer2",
        paid_amount_cents=9900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592118",
        created_ago=timedelta(days=10),
        paid_ago=timedelta(days=9),
        shipped_ago=timedelta(days=8),
        delivered_ago=timedelta(days=7),
        items=(item("mipb10"),),
        note="归属对照样本：必须始终属于 customer2，且本身可退",
    ),
    OrderSpec(
        order_no="1270189029630002",
        label="C2-02",
        username="customer2",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592119",
        created_ago=timedelta(days=5),
        paid_ago=timedelta(days=4),
        shipped_ago=timedelta(days=3),
        delivered_ago=timedelta(days=2),
        items=(item("xiaomibluetooth"),),
        note="已有待审批申请（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="1270189029630003",
        label="C2-03",
        username="customer2",
        paid_amount_cents=189900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592120",
        created_ago=timedelta(days=8),
        paid_ago=timedelta(days=7),
        shipped_ago=timedelta(days=6),
        delivered_ago=timedelta(days=4),
        items=(item("xiaomipad6"),),
        note="已有已批准申请 + 退款打款中（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="1270189029630004",
        label="C2-04",
        username="customer2",
        paid_amount_cents=6900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592121",
        created_ago=timedelta(days=12),
        paid_ago=timedelta(days=11),
        shipped_ago=timedelta(days=10),
        delivered_ago=timedelta(days=6),
        items=(item("mijiasensor"),),
        note="曾被拒绝（seed_refunds 建）→ 名额已释放，**这单仍然可退**",
    ),
    OrderSpec(
        order_no="1270189029630005",
        label="C2-05",
        username="customer2",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592122",
        created_ago=timedelta(days=13),
        paid_ago=timedelta(days=12),
        shipped_ago=timedelta(days=11),
        delivered_ago=timedelta(days=9),
        items=(item("xiaomicarcharger"),),
        note="完整退款成功：订单、申请、流水状态一致",
    ),
    OrderSpec(
        order_no="1270189029630006",
        label="C2-06",
        username="customer2",
        paid_amount_cents=0,
        payment_status=PaymentStatus.UNPAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=5),
        paid_ago=None,
        shipped_ago=None,
        delivered_ago=None,
        items=(item("mics250"),),
        note="未支付：小额单（39.00 元），customer2 视角",
    ),
    OrderSpec(
        order_no="1270189029630007",
        label="C2-07",
        username="customer2",
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592124",
        created_ago=timedelta(days=15),
        paid_ago=timedelta(days=14),
        shipped_ago=timedelta(days=13),
        # 同一时刻发货即签收：时间线允许相等，不允许倒挂。
        delivered_ago=timedelta(days=13),
        items=(item("xiaomirouterax3000"),),
        note="窗口内靠后：签收 13 天，距退款截止只剩约 1 天",
    ),
    OrderSpec(
        order_no="1270189029630008",
        label="C2-08",
        username="customer2",
        paid_amount_cents=24900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592125",
        created_ago=timedelta(days=3),
        paid_ago=timedelta(days=2),
        shipped_ago=timedelta(days=1),
        # 6 小时前刚签收：窗口的**第一天**，也是可退的。
        delivered_ago=timedelta(hours=6),
        items=(item("xiaomiband9"),),
        note="窗口起点：6 小时前刚签收；已有待审批申请（seed_refunds 建）",
    ),
    OrderSpec(
        order_no="1270189029630009",
        label="C2-09",
        username="customer2",
        paid_amount_cents=12900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.SHIPPED,
        tracking_no="SF160337592126",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=2),
        delivered_ago=None,
        items=(item("mispkplay"),),
        note="已发货未签收：在途，签收后才开始算 14 天",
    ),
    OrderSpec(
        order_no="1270189029630010",
        label="C2-10",
        username="customer2",
        paid_amount_cents=89900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592127",
        created_ago=timedelta(days=19),
        paid_ago=timedelta(days=18),
        shipped_ago=timedelta(days=17),
        delivered_ago=timedelta(days=16),
        items=(item("mijiaairpurifier4"),),
        note="超期：签收 16 天；窗口内申请曾被拒绝（seed_refunds 建）",
    ),
    OrderSpec(
        order_no="1270189029630011",
        label="C2-11",
        username="customer2",
        paid_amount_cents=39900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592128",
        created_ago=timedelta(days=24),
        paid_ago=timedelta(days=23),
        shipped_ago=timedelta(days=22),
        delivered_ago=timedelta(days=20),
        items=(item("redmibuds5pro"),),
        note="已退款：第三条完整退款链路（同一商品在客户 1 手里是可退的）",
    ),
    OrderSpec(
        order_no="1270189029630012",
        label="C2-12",
        username="customer2",
        paid_amount_cents=19800,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=2),
        paid_ago=timedelta(days=1),
        shipped_ago=None,
        delivered_ago=None,
        items=(item("xiaomimouse"), item("xiaomikeyboard")),
        note="已支付未发货 + 一单多商品（两行）：键鼠组合一起买",
    ),
    OrderSpec(
        order_no="1260918430020017", label="C1-17", username="customer1",
        paid_amount_cents=299900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD185000000017',
        created_ago=timedelta(days=7), paid_ago=timedelta(days=6), shipped_ago=timedelta(days=5), delivered_ago=timedelta(days=3),
        items=(item("robot1s"),), note="扫拖机器人：已批准，打款中",
    ),
    OrderSpec(
        order_no="1260918430020018", label="C1-18", username="customer1",
        paid_amount_cents=89800,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD185000000018',
        created_ago=timedelta(days=7), paid_ago=timedelta(days=6), shipped_ago=timedelta(days=5), delivered_ago=timedelta(days=3),
        items=(item("waterboiler5l"), item("airfryer65l"),), note="厨房家电组合：整单退款待审批",
    ),
    OrderSpec(
        order_no="1260918430020019", label="C1-19", username="customer1",
        paid_amount_cents=34900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD185000000019',
        created_ago=timedelta(days=7), paid_ago=timedelta(days=6), shipped_ago=timedelta(days=5), delivered_ago=timedelta(days=3),
        items=(item("circulationfan"),), note="风扇申请已拒绝：仍在窗口内，可重新申请",
    ),
    OrderSpec(
        order_no="1260918430020020", label="C1-20", username="customer1",
        paid_amount_cents=27600,
        payment_status=PaymentStatus.REFUNDED, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD185000000020',
        created_ago=timedelta(days=13), paid_ago=timedelta(days=12), shipped_ago=timedelta(days=11), delivered_ago=timedelta(days=9),
        items=(item("mipb10", quantity=2), item("xiaomicable6a", quantity=2),), note="多商品、多件整单退款成功",
    ),
    OrderSpec(
        order_no="1270189029630013", label="C2-13", username="customer2",
        paid_amount_cents=249900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000013',
        created_ago=timedelta(days=9), paid_ago=timedelta(days=8), shipped_ago=timedelta(days=7), delivered_ago=timedelta(days=5),
        items=(item("washer12"),), note="洗衣机：已批准，打款中",
    ),
    OrderSpec(
        order_no="1270189029630014", label="C2-14", username="customer2",
        paid_amount_cents=219900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000014',
        created_ago=timedelta(days=10), paid_ago=timedelta(days=9), shipped_ago=timedelta(days=8), delivered_ago=timedelta(days=6),
        items=(item("airconditioner"),), note="空调：已批准，打款中",
    ),
    OrderSpec(
        order_no="1270189029630015", label="C2-15", username="customer2",
        paid_amount_cents=299900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000015',
        created_ago=timedelta(days=6), paid_ago=timedelta(days=5), shipped_ago=timedelta(days=4), delivered_ago=timedelta(days=2),
        items=(item("robot1s"),), note="扫拖机器人：整单退款待审批",
    ),
    OrderSpec(
        order_no="1270189029630016", label="C2-16", username="customer2",
        paid_amount_cents=9900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000016',
        created_ago=timedelta(days=8), paid_ago=timedelta(days=7), shipped_ago=timedelta(days=6), delivered_ago=timedelta(days=4),
        items=(item("carhumidifier"),), note="车载加湿器申请已拒绝：仍可再次申请",
    ),
    OrderSpec(
        order_no="1270189029630017", label="C2-17", username="customer2",
        paid_amount_cents=0,
        payment_status=PaymentStatus.UNPAID, fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=7), paid_ago=None, shipped_ago=None, delivered_ago=None,
        items=(item("xiaomiband9"), item("mipb10"),), note="多商品未支付：实付为零，无物流",
    ),
    OrderSpec(
        order_no="1270189029630018", label="C2-18", username="customer2",
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000018',
        created_ago=timedelta(days=34), paid_ago=timedelta(days=33), shipped_ago=timedelta(days=32), delivered_ago=timedelta(days=30),
        items=(item("waterboiler5l"),), note="历史订单：签收30天，超出退款窗口",
    ),
    OrderSpec(
        order_no="1270189029630019", label="C2-19", username="customer2",
        paid_amount_cents=48700,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000019',
        created_ago=timedelta(days=5), paid_ago=timedelta(days=4), shipped_ago=timedelta(days=3), delivered_ago=timedelta(days=1),
        items=(item("circulationfan"), item("mijiasensor", quantity=2),), note="智能家居组合：签收1天，可整单退",
    ),
    OrderSpec(
        order_no="1270189029630020", label="C2-20", username="customer2",
        paid_amount_cents=6900,
        payment_status=PaymentStatus.PAID, fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no='JD285000000020',
        created_ago=timedelta(days=18), paid_ago=timedelta(days=17), shipped_ago=timedelta(days=16), delivered_ago=timedelta(days=13, hours=22),
        items=(item("xiaomicharger33w"),), note="期限边界：距14天截止约2小时，仍可退",
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
    """
    seen: set[str] = set()
    seen_labels: set[str] = set()

    for spec in DEMO_ORDERS:
        if spec.order_no in seen:
            raise ValueError(f"订单号重复：{spec.order_no}")
        seen.add(spec.order_no)

        if not spec.label:
            raise ValueError(f"{spec.order_no}: 必须给一个 label（如 C1-01）")
        if spec.label in seen_labels:
            raise ValueError(f"label 重复：{spec.label}")
        seen_labels.add(spec.label)

        if spec.created_ago is None:
            raise ValueError(f"{spec.order_no}: created_ago 必填，订单不可能没有下单时间")

        # 已支付/已退款：实付须等于明细合计；未支付实付为 0（明细是原价快照），不比对。
        if spec.payment_status is not PaymentStatus.UNPAID:
            items_total = sum(i.quantity * i.unit_price_cents for i in spec.items)
            if items_total != spec.paid_amount_cents:
                raise ValueError(
                    f"{spec.order_no}({spec.label}): paid_amount_cents="
                    f"{spec.paid_amount_cents} but items total {items_total}"
                )

        if spec.paid_ago is None and spec.payment_status is not PaymentStatus.UNPAID:
            raise ValueError(f"{spec.order_no}: 状态是 {spec.payment_status}，必须有支付时间")

        if spec.delivered_ago is None and spec.fulfillment_status is FulfillmentStatus.DELIVERED:
            raise ValueError(f"{spec.order_no}: 状态已签收，必须有签收时间")

        # 时间线换算成"多久以前"须单调不增；严格递减会误伤同一秒内的动作（如当天发货当天签收）。
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
    events = [t for t in (created_at, paid_at, shipped_at, delivered_at) if t is not None]
    order.updated_at = max(events)


async def seed(session: AsyncSession, now: datetime, refresh: bool = False):
    """在调用方事务中写入；刷新时商品明细也同步替换。"""
    _validate()
    created, refreshed, skipped = [], [], []
    user_ids = dict((await session.execute(select(User.username, User.id))).all())
    existing = {order.order_no: order for order in await session.scalars(
        select(Order).where(Order.order_no.in_([spec.order_no for spec in DEMO_ORDERS]))
    )}
    for spec in DEMO_ORDERS:
        user_id = user_ids.get(spec.username)
        if user_id is None:
            raise RuntimeError(f"Missing demo account: {spec.username}; run seed_users first")
        order = existing.get(spec.order_no)
        if order is not None and not refresh:
            skipped.append(spec)
            continue
        is_new = order is None
        if is_new:
            order = Order(order_no=spec.order_no)
            session.add(order)
        _apply(order, spec, user_id, now)
        await session.flush()
        if not is_new:
            await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
        for row in spec.items:
            session.add(OrderItem(order_id=order.id, **asdict(row),
                                 created_at=order.created_at, updated_at=order.created_at))
        (created if is_new else refreshed).append(spec)
    await session.flush()
    return created, refreshed, skipped


async def main(refresh: bool = False) -> None:
    try:
        async with SessionLocal() as session, session.begin():
            created, refreshed, skipped = await seed(session, utc_now(), refresh)
        print(f"Orders: created {len(created)}, refreshed {len(refreshed)}, skipped {len(skipped)}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(refresh="--refresh" in sys.argv[1:]))
