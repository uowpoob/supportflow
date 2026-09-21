"""创建本地演示订单与商品明细：python -m supportflow.db.seed.seed_orders。

前提：先跑过 python -m supportflow.db.seed.seed_users（订单按 username 找归属）。

加 `--refresh` 会把**已存在**的订单覆盖回本文声明的状态与时间（新增的照常插入）——
点了半天演示之后想回到干净基线，跑这个参数即可，不用手工改库。

四条硬约束，改数据时别破坏：

1. 可重复运行 —— 已存在的 order_no 直接跳过（除非 `--refresh`），不会出现第二份。
2. 时间字段一律相对当前 UTC 时间算出 —— 写死日期的话，过几天
   "签收 10 天"就变成"签收 15 天"，退款资格判定会自己翻面。
3. **时间线必须因果成立**：下单 ≤ 支付 ≤ 发货 ≤ 签收，且都不晚于现在。
   早先的版本只填了 paid/shipped/delivered，`created_at` 由 ORM 默认写成插库时刻，
   于是库里出现"9 月 16 日下单、9 月 4 日支付"这种订单 —— 演示时一眼就被看出来。
   `_validate()` 会在写库前拦住这类数据。
4. **不放故意写坏的样本**。证书异常分支（签收时间在未来、已支付但实付 0）
   由 `tests/test_refund_rules.py` 用内存对象覆盖 —— 演示库只放现实中真会出现的订单。

时间都是相对"跑种子的那一刻"锚定的，所以整套数据会随时间漂移：越靠近 14 天窗口
边界的订单，越容易在几天后翻面（可退的变成超期）。演示或验收前重新跑一次
`seed_orders --refresh` 就能重新锚定，不用手工改库。

## 编号规则

- `order_no`：16 位纯数字，**不嵌日期**。customer1 用号段 `126091843002`，
  customer2 用 `127018902963`，后 4 位是序号，例如 `1260918430020001`。
  不嵌日期是故意的：时间字段会随播种时刻漂移，单号里的日期一旦写死就跟它对不上，
  而且重复跑种子会换掉一批单号（等于每次多一批"新订单"）。
- `OrderSpec.label`：`C1-01` 这种人看的短名，**只用于注释、打印和文档**，不落库。
  库里是 16 位数字，不给人念的；写覆盖面清单时用 label 才看得清。

## 覆盖面

28 单把 `services/refunds.evaluate_eligibility` 的每个分支都点亮（括号里是命中的 code）：

    ok ─────────────── C1-01 / C1-05 / C1-06 / C1-10 / C1-12 / C1-16
                       C2-01 / C2-04 / C2-07
    window_expired ─── C1-02（签收 15 天）、C1-07（签收 14 天零 2 小时）
                       C1-13（签收 16 天）、C2-10（签收 16 天）
    order_unpaid ───── C1-03 / C2-06
    order_refunded ─── C1-04 / C1-14 / C2-11
    not_delivered ──── C1-08（未发货）、C1-09（已发货未签收）
                       C2-09（已发货未签收）、C2-12（未发货）
    already_requested ─ C1-11 / C1-15 / C2-02 / C2-03 / C2-05 / C2-08
                        （由 seed_refunds 建申请占位）

`no_payable_amount`（实付 0 却是已支付）和 `delivered_time_in_future` 两个分支**没有样本** ——
它们只可能由脏数据触发，属于单元测试的活，不放进演示库。

顺带覆盖的展示场景：一单多商品（C1-16 三行、C2-12 两行）、数量大于 1（C1-10）、
大额订单 9999.00 元（C1-01）、小额订单 39.00 元（C2-06）、无运单号（未发货的那几单）、
两个客户各有独立号段（验证归属隔离）。

## 商品目录

商品名 = 品牌 + 系列；型号 = 该系列的具体机型代码。同一个商品在不同订单里必然同名同价，
因为都从 `CATALOG` 取 —— 手抄 ItemSpec 迟早出现"同一款耳机三个名字"。
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
    # --- 手机与配件 ---
    "iphone15pm": Product("SKU-AP-IP15PM-256", "Apple iPhone 15", "Pro Max 256G", 999900),
    "iphone15case": Product("SKU-AP-IP15-CASE", "Apple iPhone 15 硅胶保护壳", "磁吸款", 39900),
    "airpodspro2": Product("SKU-AP-APP2-USBC", "Apple AirPods Pro", "第二代 USB-C", 189900),
    # --- 音频 ---
    "wh1000xm5": Product("SKU-SONY-WH1000XM5", "索尼 WH-1000XM5", "无线降噪头戴式", 289900),
    "jblgo4": Product("SKU-JBL-GO4", "JBL GO 4 便携音箱", "GO 4", 29900),
    "mispkplay": Product("SKU-MI-SPK-PLAY", "小米 蓝牙音箱 Play", "小米音箱 Play", 12900),
    # --- 电源与线材 ---
    "mipb20": Product("SKU-MI-PB20", "小米 移动电源", "20000mAh 22.5W", 12900),
    "mipb10": Product("SKU-MI-PB10", "小米 移动电源", "10000mAh 22.5W", 9900),
    "anker65w": Product("SKU-ANK-A2666", "Anker 安克 65W 氮化镓充电器", "A2666", 19900),
    "apple20w": Product("SKU-AP-A2305", "Apple 20W USB-C 电源适配器", "A2305", 14900),
    "ugreencable": Product("SKU-UG-CD137", "绿联 Type-C 数据线 2m", "CD137 100W", 5900),
    "apc05": Product("SKU-AP-C05", "Apple USB-C 转接线", "0.5m", 14900),
    # --- 电脑与办公 ---
    "asusfa507": Product("SKU-ASUS-FA507NV", "华硕 天选5 游戏本", "FA507NV", 749900),
    "matebook14": Product("SKU-HW-MB14-2024", "华为 MateBook 14", "2024 酷睿版", 549900),
    "xiaoxinpad": Product("SKU-LENOVO-TB350FU", "联想 小新 Pad", "TB350FU", 139900),
    "belkintb4": Product("SKU-BELKIN-TB4", "贝尔金 雷电 4 扩展坞", "七合一", 109800),
    "sande61": Product("SKU-SD-E61-1TB", "SanDisk 移动固态硬盘 1TB", "E61", 59900),
    "k380": Product("SKU-LOGI-K380", "罗技 K380 键盘", "多设备蓝牙版", 32900),
    "g102": Product("SKU-LOGI-G102", "罗技 G102 鼠标", "第二代", 12900),
    "c920": Product("SKU-LOGI-C920", "罗技 C920 摄像头", "C920 Pro", 49900),
    "wristrest": Product("SKU-LOGI-WR1", "罗技 键盘腕托", "记忆棉", 6900),
    "aocq27g2s": Product("SKU-AOC-Q27G2S", "AOC 27 英寸 2K 显示器", "Q27G2S", 129900),
    # --- 可穿戴与周边 ---
    "gt4_46": Product("SKU-HW-GT4-46", "华为 WATCH GT 4", "46mm 时尚款", 148800),
    "gt4_41": Product("SKU-HW-GT4-41", "华为 WATCH GT 4 时尚款", "41mm", 168800),
    "tplinkxdr": Product("SKU-TP-XDR3010", "TP-LINK AX3000 路由器", "TL-XDR3010", 22900),
    "mics250": Product("SKU-MI-CS250", "小米 液态硅胶手机壳", "小米 14 款", 3900),
    "ankcarmount": Product("SKU-ANK-A2735", "安克 车载手机支架", "A2735", 9900),
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
    # ------------------------------ customer1（号段 126091843002） ------------------------------
    OrderSpec(
        order_no="1260918430020001",
        label="C1-01",
        username="customer1",
        paid_amount_cents=999900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467219",
        created_ago=timedelta(days=13),
        paid_ago=timedelta(days=12),
        shipped_ago=timedelta(days=11),
        delivered_ago=timedelta(days=10),
        items=(item("iphone15pm"),),
        note="基准可退单：签收 10 天；大额 9999.00 元",
    ),
    OrderSpec(
        order_no="1260918430020002",
        label="C1-02",
        username="customer1",
        paid_amount_cents=189900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467220",
        created_ago=timedelta(days=18),
        paid_ago=timedelta(days=17),
        shipped_ago=timedelta(days=16),
        delivered_ago=timedelta(days=15),
        items=(item("airpodspro2"),),
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
        paid_amount_cents=5900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467222",
        created_ago=timedelta(days=22),
        paid_ago=timedelta(days=21),
        shipped_ago=timedelta(days=20),
        delivered_ago=timedelta(days=18),
        items=(item("ugreencable"),),
        note="已退款：完整退款链路（申请/审批/流水），永久不能重复申请",
    ),
    OrderSpec(
        order_no="1260918430020005",
        label="C1-05",
        username="customer1",
        paid_amount_cents=289900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467223",
        created_ago=timedelta(days=7),
        paid_ago=timedelta(days=6),
        shipped_ago=timedelta(days=4),
        delivered_ago=timedelta(days=3),
        items=(item("wh1000xm5"),),
        note="基准可退单：签收 3 天，头戴式降噪耳机",
    ),
    OrderSpec(
        order_no="1260918430020006",
        label="C1-06",
        username="customer1",
        paid_amount_cents=32900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467224",
        created_ago=timedelta(days=16),
        paid_ago=timedelta(days=15),
        shipped_ago=timedelta(days=14),
        # ⚠️ 这里**不能**写"恰好 14 天"：时间是相对播种那一刻算出来的，
        # 秒针一走就变成 14 天零几秒，判定立刻翻面成超期。
        # 精确边界（14 天整允许、14 天零 1 微秒拒绝）由针对纯函数的单元测试覆盖，
        # 演示数据只负责"窗口快到期"这种稳定可观察的状态。
        delivered_ago=timedelta(days=13),
        items=(item("k380"),),
        note="窗口内靠后：签收 13 天，距退款截止只剩约 1 天",
    ),
    OrderSpec(
        order_no="1260918430020007",
        label="C1-07",
        username="customer1",
        paid_amount_cents=12900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467225",
        created_ago=timedelta(days=17),
        paid_ago=timedelta(days=16),
        shipped_ago=timedelta(days=15),
        # 窗口关闭 2 小时 —— 和 C1-06 配对：一个还在窗口内、一个刚出窗口。
        delivered_ago=timedelta(days=14, hours=2),
        items=(item("g102"),),
        note="刚过窗口：签收 14 天零 2 小时，退款窗口已关闭",
    ),
    OrderSpec(
        order_no="1260918430020008",
        label="C1-08",
        username="customer1",
        paid_amount_cents=749900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=3),
        paid_ago=timedelta(days=2),
        shipped_ago=None,
        delivered_ago=None,
        items=(item("asusfa507"),),
        note="已支付未发货：大额游戏本，付款了但还没签收",
    ),
    OrderSpec(
        order_no="1260918430020009",
        label="C1-09",
        username="customer1",
        paid_amount_cents=49900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.SHIPPED,
        tracking_no="SF150238467227",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=1),
        delivered_ago=None,
        items=(item("c920"),),
        note="已发货未签收：在途，签收后才开始算 14 天",
    ),
    OrderSpec(
        order_no="1260918430020010",
        label="C1-10",
        username="customer1",
        # 两件同一商品：149.00 × 2 = 298.00。
        paid_amount_cents=29800,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467228",
        created_ago=timedelta(days=9),
        paid_ago=timedelta(days=8),
        shipped_ago=timedelta(days=7),
        delivered_ago=timedelta(days=6),
        items=(item("apple20w", quantity=2),),
        note="数量大于 1：同一商品买了两件，签收 6 天",
    ),
    OrderSpec(
        order_no="1260918430020011",
        label="C1-11",
        username="customer1",
        paid_amount_cents=129900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467229",
        created_ago=timedelta(days=11),
        paid_ago=timedelta(days=10),
        shipped_ago=timedelta(days=9),
        delivered_ago=timedelta(days=8),
        items=(item("aocq27g2s"),),
        note="已有已批准申请 + 退款打款中（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="1260918430020012",
        label="C1-12",
        username="customer1",
        paid_amount_cents=148800,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467230",
        created_ago=timedelta(days=4),
        paid_ago=timedelta(days=3),
        shipped_ago=timedelta(days=2),
        delivered_ago=timedelta(days=1),
        items=(item("gt4_46"),),
        note="曾被拒绝（seed_refunds 建）→ 名额已释放，**这单仍然可退**",
    ),
    OrderSpec(
        order_no="1260918430020013",
        label="C1-13",
        username="customer1",
        paid_amount_cents=39900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467231",
        created_ago=timedelta(days=20),
        paid_ago=timedelta(days=19),
        shipped_ago=timedelta(days=18),
        delivered_ago=timedelta(days=16),
        items=(item("iphone15case"),),
        note="超期（小额）：签收 16 天，手机壳这类低价配件也走同一套规则",
    ),
    OrderSpec(
        order_no="1260918430020014",
        label="C1-14",
        username="customer1",
        paid_amount_cents=549900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467232",
        created_ago=timedelta(days=26),
        paid_ago=timedelta(days=25),
        shipped_ago=timedelta(days=24),
        delivered_ago=timedelta(days=22),
        items=(item("matebook14"),),
        note="已退款（大额笔记本）：第二条完整退款链路",
    ),
    OrderSpec(
        order_no="1260918430020015",
        label="C1-15",
        username="customer1",
        paid_amount_cents=19900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467233",
        created_ago=timedelta(days=5),
        paid_ago=timedelta(days=4),
        shipped_ago=timedelta(days=3),
        delivered_ago=timedelta(days=2),
        items=(item("anker65w"),),
        note="已有待审批申请（seed_refunds 建）→ 管理侧待办里能批到这条",
    ),
    OrderSpec(
        order_no="1260918430020016",
        label="C1-16",
        username="customer1",
        # 1098.00 + 149.00×2 + 69.00 = 1465.00。
        paid_amount_cents=146500,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF150238467234",
        created_ago=timedelta(days=6),
        paid_ago=timedelta(days=5),
        shipped_ago=timedelta(days=4),
        delivered_ago=timedelta(days=2),
        items=(
            item("belkintb4"),
            item("apc05", quantity=2),
            item("wristrest"),
        ),
        note="一单多商品（三行）+ 数量大于 1：签收 2 天，合计 1465.00 元",
    ),
    # ------------------------------ customer2（号段 127018902963） ------------------------------
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
        paid_amount_cents=29900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592119",
        created_ago=timedelta(days=5),
        paid_ago=timedelta(days=4),
        shipped_ago=timedelta(days=3),
        delivered_ago=timedelta(days=2),
        items=(item("jblgo4"),),
        note="已有待审批申请（seed_refunds 建）→ already_requested",
    ),
    OrderSpec(
        order_no="1270189029630003",
        label="C2-03",
        username="customer2",
        paid_amount_cents=139900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592120",
        created_ago=timedelta(days=8),
        paid_ago=timedelta(days=7),
        shipped_ago=timedelta(days=6),
        delivered_ago=timedelta(days=4),
        items=(item("xiaoxinpad"),),
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
        items=(item("wristrest"),),
        note="曾被拒绝（seed_refunds 建）→ 名额已释放，**这单仍然可退**",
    ),
    OrderSpec(
        order_no="1270189029630005",
        label="C2-05",
        username="customer2",
        paid_amount_cents=9900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592122",
        created_ago=timedelta(days=13),
        paid_ago=timedelta(days=12),
        shipped_ago=timedelta(days=11),
        delivered_ago=timedelta(days=9),
        items=(item("ankcarmount"),),
        note="已有已批准申请 + 打款成功（seed_refunds 建）→ already_requested",
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
        paid_amount_cents=22900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592124",
        created_ago=timedelta(days=15),
        paid_ago=timedelta(days=14),
        shipped_ago=timedelta(days=13),
        # 同一时刻发货即签收：时间线允许相等，不允许倒挂。
        delivered_ago=timedelta(days=13),
        items=(item("tplinkxdr"),),
        note="窗口内靠后：签收 13 天，距退款截止只剩约 1 天",
    ),
    OrderSpec(
        order_no="1270189029630008",
        label="C2-08",
        username="customer2",
        paid_amount_cents=168800,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592125",
        created_ago=timedelta(days=3),
        paid_ago=timedelta(days=2),
        shipped_ago=timedelta(days=1),
        # 6 小时前刚签收：窗口的**第一天**，也是可退的。
        delivered_ago=timedelta(hours=6),
        items=(item("gt4_41"),),
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
        paid_amount_cents=59900,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592127",
        created_ago=timedelta(days=19),
        paid_ago=timedelta(days=18),
        shipped_ago=timedelta(days=17),
        delivered_ago=timedelta(days=16),
        items=(item("sande61"),),
        note="超期：签收 16 天；有一次超期后被拒的申请（seed_refunds 建）",
    ),
    OrderSpec(
        order_no="1270189029630011",
        label="C2-11",
        username="customer2",
        paid_amount_cents=289900,
        payment_status=PaymentStatus.REFUNDED,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        tracking_no="SF160337592128",
        created_ago=timedelta(days=24),
        paid_ago=timedelta(days=23),
        shipped_ago=timedelta(days=22),
        delivered_ago=timedelta(days=20),
        items=(item("wh1000xm5"),),
        note="已退款：第三条完整退款链路（同一商品在客户 1 手里是可退的）",
    ),
    OrderSpec(
        order_no="1270189029630012",
        label="C2-12",
        username="customer2",
        # 129.00 + 329.00 = 458.00。
        paid_amount_cents=45800,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNSHIPPED,
        tracking_no=None,
        created_ago=timedelta(days=2),
        paid_ago=timedelta(days=1),
        shipped_ago=None,
        delivered_ago=None,
        items=(item("g102"), item("k380")),
        note="已支付未发货 + 一单多商品（两行）：键鼠套装一起买",
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

        # 已支付 / 已退款订单的实付必须等于明细合计。
        # 未支付订单实付为 0，明细是其原价快照，不参与比对。
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

        # 时间线：越靠后的环节，距今越近。换算成"多久以前"就是**单调不增**。
        # 写成"必须严格递减"会误伤同一秒内完成的动作（比如当天发货当天签收）。
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

                    for row in spec.items:
                        session.add(OrderItem(order_id=order.id, **asdict(row)))

                    created.append(spec)

        total_rows = sum(len(spec.items) for spec in created)
        print(
            f"Orders: created {len(created)}, refreshed {len(refreshed)}, "
            f"skipped {len(skipped)}; {total_rows} item row(s) inserted."
        )
        if skipped and not refresh:
            print("（想把这些订单覆盖回声明状态，加 --refresh 重跑）")
        # 打印覆盖清单：种子跑完直接对着它核对"该覆盖的场景是不是都在"。
        for spec in (*created, *refreshed):
            print(
                f"  {spec.label} order_no={spec.order_no} owner={spec.username} "
                f"paid_cents={spec.paid_amount_cents} "
                f"payment={spec.payment_status.value} "
                f"fulfillment={spec.fulfillment_status.value} "
                f"| {spec.note}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(refresh="--refresh" in sys.argv[1:]))
