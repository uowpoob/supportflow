"""小米演示退款：20条申请，四种申请状态各5条。

15条审批，10条流水（5条打款中、5条成功），不模拟打款失败或重试。
申请、审批、流水和订单状态一致；整单金额取订单实付。
完整刷新用 python -m supportflow.db.seed.seed_demo --refresh。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.db.session import SessionLocal, engine
from supportflow.models import (
    Conversation,
    Order,
    RefundApproval,
    RefundRecord,
    RefundRequest,
    User,
)
from supportflow.models.enums import (
    ApprovalDecision,
    PaymentStatus,
    RefundExecutionStatus,
    RefundStatus,
)


@dataclass(frozen=True)
class ApprovalSpec:
    decision: ApprovalDecision
    comment: str
    decided_ago: timedelta


@dataclass(frozen=True)
class RecordSpec:
    status: RefundExecutionStatus
    attempt_count: int
    created_ago: timedelta
    succeeded_ago: timedelta | None


@dataclass(frozen=True)
class RefundSpec:
    # 申请号序号：request_key / refund_no 的后 4 位都由它算出来。
    key_no: int
    order_no: str
    status: RefundStatus
    reason: str
    created_ago: timedelta
    note: str
    label: str = ""
    approval: ApprovalSpec | None = None
    record: RecordSpec | None = None


DEMO_REFUNDS: tuple[RefundSpec, ...] = (
    RefundSpec(
        key_no=1,
        order_no="1260918430020004",
        label="C1-04",
        status=RefundStatus.REFUNDED,
        reason="线材接触不良，充电时断时续，换了插座也一样",
        created_ago=timedelta(days=17),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="已核实为线材本身问题，同意退款",
            decided_ago=timedelta(days=16),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.SUCCEEDED,
            attempt_count=1,
            created_ago=timedelta(days=16),
            succeeded_ago=timedelta(days=16),
        ),
        note="完整闭环：线材，订单已退款，退款流水成功",
    ),
    RefundSpec(
        key_no=3,
        order_no="1260918430020014",
        label="C1-14",
        status=RefundStatus.REFUNDED,
        reason="屏幕右上角有一处亮点，暗屏时很明显",
        created_ago=timedelta(days=21),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="属外观质量问题，按整单退款处理",
            decided_ago=timedelta(days=20),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.SUCCEEDED,
            attempt_count=1,
            created_ago=timedelta(days=20),
            succeeded_ago=timedelta(days=20),
        ),
        note="完整闭环（大额笔记本 4499.00 元），订单已退款",
    ),
    RefundSpec(
        key_no=11,
        order_no="1270189029630011",
        label="C2-11",
        status=RefundStatus.REFUNDED,
        reason="左耳没有声音，右耳正常",
        created_ago=timedelta(days=19),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="检测为单侧单元故障，同意退款",
            decided_ago=timedelta(days=18),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.SUCCEEDED,
            attempt_count=1,
            created_ago=timedelta(days=18),
            succeeded_ago=timedelta(days=18),
        ),
        note="完整闭环：同款耳机在 customer2 手里已退款",
    ),
    RefundSpec(
        key_no=2,
        order_no="1260918430020011",
        label="C1-11",
        status=RefundStatus.APPROVED,
        reason="右下角有一小块暗斑，看视频时比较明显",
        created_ago=timedelta(days=6),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="已确认坏点，同意退款",
            decided_ago=timedelta(days=5),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.PROCESSING,
            attempt_count=1,
            created_ago=timedelta(days=5),
            succeeded_ago=None,
        ),
        note="已批准、退款打款中：覆盖 refund_records 的 processing 状态",
    ),
    RefundSpec(
        key_no=7,
        order_no="1270189029630003",
        label="C2-03",
        status=RefundStatus.APPROVED,
        reason="屏幕边缘触控不灵，返回手势经常没反应",
        created_ago=timedelta(days=3),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="情况属实，同意退款",
            decided_ago=timedelta(days=2),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.PROCESSING,
            attempt_count=1,
            created_ago=timedelta(days=2),
            succeeded_ago=None,
        ),
        note="已批准、退款打款中：管理侧第二条待打款流水",
    ),
    RefundSpec(
        key_no=9,
        order_no="1270189029630005",
        label="C2-05",
        status=RefundStatus.REFUNDED,
        reason="手机放上车充后无法充电，换另一部支持无线充电的手机也不行",
        created_ago=timedelta(days=8),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="同意退款",
            decided_ago=timedelta(days=7),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.SUCCEEDED,
            attempt_count=1,
            created_ago=timedelta(days=7),
            succeeded_ago=timedelta(days=6),
        ),
        note="车充退款成功：申请、订单均已退款，流水成功",
    ),
    RefundSpec(
        key_no=4,
        order_no="1260918430020015",
        label="C1-15",
        status=RefundStatus.PENDING,
        reason="插上后指示灯不亮，换插座和数据线都不行",
        created_ago=timedelta(days=1),
        note="待审批：管理侧待办 + 客户侧显示进度，订单因此不可重复申请",
    ),
    RefundSpec(
        key_no=6,
        order_no="1270189029630002",
        label="C2-02",
        status=RefundStatus.PENDING,
        reason="开机后连不上手机蓝牙，重置过一次还是不行",
        created_ago=timedelta(days=1),
        note="待审批：第二条待办，customer2 视角",
    ),
    RefundSpec(
        key_no=10,
        order_no="1270189029630008",
        label="C2-08",
        status=RefundStatus.PENDING,
        reason="表盘和表带连接处有松动，戴着手腕能感觉到晃",
        created_ago=timedelta(hours=2),
        note="待审批：刚签收 6 小时就提交的申请，管理侧最新一条待办",
    ),
    RefundSpec(
        key_no=5,
        order_no="1260918430020012",
        label="C1-12",
        status=RefundStatus.REJECTED,
        reason="戴着出汗以后表带内侧有点发白，看着不舒服",
        created_ago=timedelta(hours=12),
        approval=ApprovalSpec(
            decision=ApprovalDecision.REJECTED,
            comment="表带发白属正常使用痕迹，非质量问题，不符合退款条件",
            decided_ago=timedelta(hours=6),
        ),
        note="被拒绝：名额已释放，这一单**仍然可以再次提交申请**（判定为 ok）",
    ),
    RefundSpec(
        key_no=8,
        order_no="1270189029630004",
        label="C2-04",
        status=RefundStatus.REJECTED,
        reason="温湿度计显示与空调设定温度不一致，要求退款",
        created_ago=timedelta(days=5),
        approval=ApprovalSpec(
            decision=ApprovalDecision.REJECTED,
            comment="检测读数正常，空调设定温度不等于室内实测温度，本次质量问题申请不予批准",
            decided_ago=timedelta(days=4),
        ),
        note="被拒绝：名额已释放，这一单**仍然可以再次提交申请**（判定为 ok）",
    ),
    RefundSpec(
        key_no=12,
        order_no="1270189029630010",
        label="C2-10",
        status=RefundStatus.REJECTED,
        reason="买了之后一直没用上，想退掉",
        created_ago=timedelta(days=14),
        approval=ApprovalSpec(
            decision=ApprovalDecision.REJECTED,
            comment="无质量问题且商品已有明显使用痕迹，本次申请不予批准",
            decided_ago=timedelta(days=13),
        ),
        note="窗口内申请被拒绝，当前签收已16天，不能再申请",
    ),
    RefundSpec(
        key_no=13, order_no="1260918430020017", label="C1-17",
        status=RefundStatus.APPROVED, reason="扫拖机器人回到基站后无法自动清洗拖布", created_ago=timedelta(days=2),
        approval=ApprovalSpec(ApprovalDecision.APPROVED, "检测确认质量问题，同意整单退款", timedelta(days=1)),
        record=RecordSpec(RefundExecutionStatus.PROCESSING, 1, timedelta(days=1), None),
        note="机器人：整单退款已批准，打款中",
    ),
    RefundSpec(
        key_no=14, order_no="1260918430020018", label="C1-18",
        status=RefundStatus.PENDING, reason="电热水瓶按出水键不出水，申请厨房家电组合整单退货退款", created_ago=timedelta(days=1),
        note="两种厨房家电：整单退款待审批",
    ),
    RefundSpec(
        key_no=15, order_no="1260918430020019", label="C1-19",
        status=RefundStatus.REJECTED, reason="风扇开启摇头后有轻微电机声，认为是质量问题", created_ago=timedelta(days=2),
        approval=ApprovalSpec(ApprovalDecision.REJECTED, "检测运行正常，轻微工作声不构成质量故障，本次申请拒绝", timedelta(days=1)),
        note="拒绝后可再次申请",
    ),
    RefundSpec(
        key_no=16, order_no="1260918430020020", label="C1-20",
        status=RefundStatus.REFUNDED, reason="两件移动电源均无法正常充电，连同数据线一起退货", created_ago=timedelta(days=7),
        approval=ApprovalSpec(ApprovalDecision.APPROVED, "检测确认质量问题，同意整单退款", timedelta(days=6)),
        record=RecordSpec(RefundExecutionStatus.SUCCEEDED, 1, timedelta(days=6), timedelta(days=6)),
        note="多商品多件：整单退款成功",
    ),
    RefundSpec(
        key_no=17, order_no="1270189029630013", label="C2-13",
        status=RefundStatus.APPROVED, reason="洗衣机运行时持续报错，按说明排查后仍无法洗涤", created_ago=timedelta(days=4),
        approval=ApprovalSpec(ApprovalDecision.APPROVED, "检测确认质量问题，同意整单退款", timedelta(days=3)),
        record=RecordSpec(RefundExecutionStatus.PROCESSING, 1, timedelta(days=3), None),
        note="洗衣机：退款已批准，打款中",
    ),
    RefundSpec(
        key_no=18, order_no="1270189029630014", label="C2-14",
        status=RefundStatus.APPROVED, reason="空调安装后无法正常制冷，售后检测确认设备故障", created_ago=timedelta(days=4),
        approval=ApprovalSpec(ApprovalDecision.APPROVED, "检测确认质量问题，同意整单退款", timedelta(days=3)),
        record=RecordSpec(RefundExecutionStatus.PROCESSING, 1, timedelta(days=3), None),
        note="空调：退款已批准，打款中",
    ),
    RefundSpec(
        key_no=19, order_no="1270189029630015", label="C2-15",
        status=RefundStatus.PENDING, reason="扫拖机器人清水箱装好后持续提示缺水", created_ago=timedelta(days=1),
        note="机器人：待审批",
    ),
    RefundSpec(
        key_no=20, order_no="1270189029630016", label="C2-16",
        status=RefundStatus.REJECTED, reason="加湿器使用香薰液后堵塞，要求按质量问题退款", created_ago=timedelta(days=3),
        approval=ApprovalSpec(ApprovalDecision.REJECTED, "检测发现非规定介质导致堵塞，本次质量问题申请拒绝", timedelta(days=2)),
        note="使用不当被拒绝，仍在申请窗口内",
    ),
)


REQUEST_KEY_HEAD = "409928517733"
REFUND_NO_HEAD = "711845902664"


def _request_key(key_no: int) -> str:
    """写死的申请编号，跑第二遍时靠它判重（不用随机 UUID）。"""
    return f"{REQUEST_KEY_HEAD}{key_no:04d}"


def _refund_no(key_no: int) -> str:
    return f"{REFUND_NO_HEAD}{key_no:04d}"


def _conversation_id(order_no: str) -> str:
    """会话 id 也用确定值，重复运行不会每跑一次多出一条会话。

    取 uuid5 而不是随便拼字符串 —— 这个 id 以后要当 PostgreSQL checkpoint 的
    thread_id 用，形状得和真实会话一致。
    """
    return str(uuid5(NAMESPACE_URL, f"supportflow-demo-conversation-{order_no}"))


def _at(now: datetime, ago: timedelta) -> datetime:
    return now - ago


def _validate() -> None:
    """自检：编号不重复、申请状态和订单支付状态对得上、审批不早于申请。

    第二条尤其重要 —— 如果声明"这条申请已退款完成"，订单就必须真的是 refunded。
    两边不一致的话，演示时会出现"申请显示已退款、订单却还能再申请"这种自相矛盾。
    """
    seen_orders: set[str] = set()
    seen_numbers: set[int] = set()
    from supportflow.db.seed.seed_orders import DEMO_ORDERS

    orders = {spec.order_no: spec for spec in DEMO_ORDERS}

    for spec in DEMO_REFUNDS:
        if spec.order_no in seen_orders:
            raise ValueError(f"同一订单出现两条演示申请：{spec.order_no}")
        seen_orders.add(spec.order_no)

        if spec.key_no in seen_numbers:
            raise ValueError(f"key_no 重复：{spec.key_no}（申请号会撞）")
        seen_numbers.add(spec.key_no)

        if not spec.label:
            raise ValueError(f"{spec.order_no}: 必须给一个 label（如 C1-04）")

        # 待审批的申请不可能已经有审批结论。
        if spec.status is RefundStatus.PENDING and (spec.approval is not None or spec.record is not None):
            raise ValueError(f"{spec.order_no}: 待审批不该有审批记录或退款流水")

        # 有审批结论（批准/拒绝）就必须有审批记录，否则管理侧的审批记录页会缺行。
        if spec.status in (RefundStatus.APPROVED, RefundStatus.REFUNDED, RefundStatus.REJECTED):
            if spec.approval is None:
                raise ValueError(f"{spec.order_no}: 状态是 {spec.status.value}，必须有审批记录")

        # 申请已走完退款闭环 → 订单必须已经翻成已退款。
        if spec.status is RefundStatus.REFUNDED:
            if spec.record is None or spec.record.status is not RefundExecutionStatus.SUCCEEDED:
                raise ValueError(
                    f"{spec.order_no}: 申请已 refunded，必须配一条 succeeded 的退款流水"
                )

        # 被拒绝的申请不该产生退款流水。
        if spec.status is RefundStatus.REJECTED and spec.record is not None:
            raise ValueError(f"{spec.order_no}: 被拒绝的申请不该产生退款流水")

        # 已批准的演示申请产生打款中流水；成功后申请状态必须变成 refunded。
        if spec.status is RefundStatus.APPROVED and spec.record is None:
            raise ValueError(f"{spec.order_no}: 已批准就该有 processing 退款流水")

        # 申请时间早于审批时间就是错的（先去申请，才有人批）。
        if spec.approval is not None and spec.approval.decided_ago > spec.created_ago:
            raise ValueError(
                f"{spec.order_no}: 审批时间早于申请时间"
                "（decided_ago 应小于 created_ago）"
            )

        order = orders[spec.order_no]
        if order.label != spec.label or order.delivered_ago is None:
            raise ValueError(f"{spec.label}: 退款必须关联同标签的已签收订单")
        if not timedelta(0) <= spec.created_ago <= order.delivered_ago:
            raise ValueError(f"{spec.label}: 申请时间必须在签收之后、当前时间之前")
        if order.delivered_ago - spec.created_ago > timedelta(days=14):
            raise ValueError(f"{spec.label}: 申请提交时已超过14天窗口")
        payment = PaymentStatus.REFUNDED if spec.status is RefundStatus.REFUNDED else PaymentStatus.PAID
        if order.payment_status is not payment:
            raise ValueError(f"{spec.label}: 订单与退款状态不一致")
        if spec.approval:
            decision = ApprovalDecision.REJECTED if spec.status is RefundStatus.REJECTED else ApprovalDecision.APPROVED
            if spec.approval.decision is not decision or spec.approval.decided_ago < timedelta(0):
                raise ValueError(f"{spec.label}: 审批结论或时间不正确")
        if spec.record:
            record = spec.record
            expected = RefundExecutionStatus.SUCCEEDED if spec.status is RefundStatus.REFUNDED else RefundExecutionStatus.PROCESSING
            if record.status is not expected or record.attempt_count != 1:
                raise ValueError(f"{spec.label}: 仅模拟一次执行的打款中或成功流水")
            if spec.approval is None or not timedelta(0) <= record.created_ago <= spec.approval.decided_ago:
                raise ValueError(f"{spec.label}: 流水时间必须在批准后")
            if record.status is RefundExecutionStatus.SUCCEEDED:
                if record.succeeded_ago is None or not timedelta(0) <= record.succeeded_ago <= record.created_ago:
                    raise ValueError(f"{spec.label}: 成功流水必须有正确的成功时间")
            elif record.succeeded_ago is not None:
                raise ValueError(f"{spec.label}: 打款中的流水不能有成功时间")


async def seed(session: AsyncSession, now: datetime):
    """在调用方事务内写入，申请号稳定，已存在的申请跳过。"""
    _validate()
    created, skipped = [], []
    admin_id = await session.scalar(
        select(User.id).where(User.username == "admin")
    )
    if admin_id is None:
        raise RuntimeError(
            "Missing demo account: admin; "
            "run python -m supportflow.db.seed.seed_users first"
        )

    orders = {
        order.order_no: order
        for order in await session.scalars(
            select(Order).where(
                Order.order_no.in_([spec.order_no for spec in DEMO_REFUNDS])
            )
        )
    }
    existing_keys = set(
        await session.scalars(
            select(RefundRequest.request_key).where(
                RefundRequest.request_key.in_(
                    [_request_key(s.key_no) for s in DEMO_REFUNDS]
                )
            )
        )
    )

    for spec in DEMO_REFUNDS:
        if _request_key(spec.key_no) in existing_keys:
            skipped.append(spec)
            print(f"Skipped existing refund request: {_request_key(spec.key_no)}")
            continue

        order = orders.get(spec.order_no)
        if order is None:
            raise RuntimeError(
                f"Missing demo order: {spec.order_no} ({spec.label}); "
                "run python -m supportflow.db.seed.seed_orders first"
            )

        # 申请必须发生在签收之后 —— 签收前不存在"退款窗口"。
        if order.delivered_at is not None:
            created_at = _at(now, spec.created_ago)
            if created_at < order.delivered_at:
                raise ValueError(
                    f"{spec.order_no}: 申请时间早于签收时间"
                    f"（签收 {order.delivered_at}，申请 {created_at}）"
                )

        if spec.status is RefundStatus.REFUNDED and (
            order.payment_status is not PaymentStatus.REFUNDED
        ):
            raise ValueError(
                f"{spec.order_no}: 声明申请已退款完成，"
                f"但订单支付状态是 {order.payment_status.value}"
            )
        if spec.status is not RefundStatus.REFUNDED and (
            order.payment_status is not PaymentStatus.PAID
        ):
            raise ValueError(
                f"{spec.order_no}: 未走完退款的申请要求订单是已支付状态，"
                f"实际是 {order.payment_status.value}"
            )

        # 退款申请外键指向会话：真实流程由 create_refund_request 建，这里补一条，标题用订单号便于对号。
        conversation_id = _conversation_id(spec.order_no)
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            conversation = Conversation(id=conversation_id, user_id=order.user_id)
            session.add(conversation)
        if conversation.user_id != order.user_id:
            raise ValueError(f"{spec.label}: 演示售后会话归属不匹配")
        conversation.title = f"{order.order_no} {spec.reason[:36]}"
        conversation.created_at = _at(now, spec.created_ago)
        conversation.updated_at = _at(now, spec.created_ago)

        await session.flush()

        latest_ago = min(
            spec.created_ago,
            spec.approval.decided_ago if spec.approval else spec.created_ago,
            spec.record.succeeded_ago if spec.record and spec.record.succeeded_ago is not None else spec.created_ago,
        )
        if spec.status is RefundStatus.REFUNDED:
            order.updated_at = _at(now, latest_ago)

        request = RefundRequest(
            request_key=_request_key(spec.key_no),
            order_id=order.id,
            conversation_id=conversation_id,
            # 金额取订单实付，和线上规则一致：请求体里没有金额这个字段。
            amount_cents=order.paid_amount_cents,
            reason_original=spec.reason,
            reason_category="quality_issue",
            status=spec.status,
            created_at=_at(now, spec.created_ago),
            updated_at=_at(now, latest_ago),
        )
        session.add(request)
        # flush 拿到自增 id，审批与流水才能引用它（此时还没提交）。
        await session.flush()

        if spec.approval is not None:
            session.add(
                RefundApproval(
                    refund_request_id=request.id,
                    admin_id=admin_id,
                    decision=spec.approval.decision,
                    comment=spec.approval.comment,
                    created_at=_at(now, spec.approval.decided_ago),
                    updated_at=_at(now, spec.approval.decided_ago),
                )
            )

        if spec.record is not None:
            session.add(
                RefundRecord(
                    refund_request_id=request.id,
                    refund_no=_refund_no(spec.key_no),
                    amount_cents=order.paid_amount_cents,
                    status=spec.record.status,
                    attempt_count=spec.record.attempt_count,
                    last_error=None,
                    succeeded_at=(
                        None
                        if spec.record.succeeded_ago is None
                        else _at(now, spec.record.succeeded_ago)
                    ),
                    created_at=_at(now, spec.record.created_ago),
                    updated_at=_at(now, spec.record.succeeded_ago or spec.record.created_ago),
                )
            )

        created.append(spec)

    await session.flush()
    return created, skipped


async def main() -> None:
    try:
        async with SessionLocal() as session, session.begin():
            created, skipped = await seed(session, utc_now())
        print(f"Refund requests: created {len(created)}, skipped {len(skipped)}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
