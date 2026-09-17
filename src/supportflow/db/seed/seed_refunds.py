"""创建本地演示退款数据：python -m supportflow.db.seed.seed_refunds。

前提：先跑过 python -m supportflow.db.seed.seed_users 和 seed_orders
（本模块按 order_no 找订单，金额也直接取自订单实付）。

为什么订单之外还要单独一个种子：退款申请的状态**不可能**只靠 orders 表造出来。
`evaluate_eligibility` 里有三个分支（已有申请 / 已批准 / 已退款）必须库里真的存在
一条申请才会命中，管理侧的"待办、审批记录、退款流水"三个页面也一样 ——
不灌这五条数据，这些页面在演示时永远是空的，看起来就像没做完。

和 seed_orders 一样守两条约束：
1. 可重复运行 —— `request_key` 是写死的 `demo-rq-<订单号>`，已存在就跳过。
2. 时间字段相对当前时间算，并且**必须晚于该订单的签收时间** ——
   签收之前不可能发起退款申请，这条也有自检。

金额一律取 `orders.paid_amount_cents`，和线上 `create_refund_request` 的规则一致 ——
演示数据也不该走一条"可以手填金额"的旁路，否则测出来的东西和线上不是一回事。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

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
    last_error: str | None = None


@dataclass(frozen=True)
class RefundSpec:
    order_no: str
    status: RefundStatus
    reason: str
    created_ago: timedelta
    note: str
    approval: ApprovalSpec | None = None
    record: RecordSpec | None = None


# 五条数据把退款申请的四个人生阶段 + 退款执行的两个结果都铺满：
#
#   pending  ── B1002：管理侧"待办"页有东西可批，客户侧显示"待审批"
#   approved ── B1003：已批准、退款执行中（processing）
#   rejected ── B1004：被拒后名额释放 —— 这一单**仍然可以再次申请**
#   approved ── B1005：已批准但打款失败（failed）—— 覆盖"执行失败"的展示
#   refunded ── A1004：完整闭环（申请/审批/流水全部成功），订单状态已翻成 refunded
#
# ⚠️ 时间必须晚于对应订单的签收时间（见下方 `_validate`），
# 否则会出现"还没签收就申请退款"的申请记录。
DEMO_REFUNDS: tuple[RefundSpec, ...] = (
    RefundSpec(
        order_no="A1004",
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
        note="完整闭环：订单已退款（refunded），退款流水成功",
    ),
    RefundSpec(
        order_no="B1002",
        status=RefundStatus.PENDING,
        reason="右声道有杂音，左耳正常",
        created_ago=timedelta(days=1),
        note="待审批：管理侧待办 + 客户侧显示进度，订单因此不可重复申请",
    ),
    RefundSpec(
        order_no="B1003",
        status=RefundStatus.APPROVED,
        reason="支架卡扣断裂，平板放上去会往下滑",
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
        note="已批准、退款执行中：覆盖 refund_records 的 processing 状态",
    ),
    RefundSpec(
        order_no="B1004",
        status=RefundStatus.REJECTED,
        reason="腕托有异味，闻着不舒服",
        created_ago=timedelta(days=5),
        approval=ApprovalSpec(
            decision=ApprovalDecision.REJECTED,
            comment="经核实非商品质量问题，不符合退款条件",
            decided_ago=timedelta(days=4),
        ),
        note="被拒绝：名额已释放，这一单仍然可以再次提交申请",
    ),
    RefundSpec(
        order_no="B1005",
        status=RefundStatus.APPROVED,
        reason="吸盘固定不住，过减速带就掉",
        created_ago=timedelta(days=8),
        approval=ApprovalSpec(
            decision=ApprovalDecision.APPROVED,
            comment="同意退款",
            decided_ago=timedelta(days=7),
        ),
        record=RecordSpec(
            status=RefundExecutionStatus.FAILED,
            attempt_count=2,
            created_ago=timedelta(days=7),
            succeeded_ago=None,
            last_error="支付渠道超时，等待重试",
        ),
        note="已批准但打款失败：覆盖 refund_records 的 failed 状态与 last_error",
    ),
)


def _request_key(order_no: str) -> str:
    """写死的申请编号，跑第二遍时靠它判重（不用随机 UUID）。"""
    return f"demo-rq-{order_no}"


def _refund_no(order_no: str) -> str:
    return f"demo-rfn-{order_no}"


def _conversation_id(order_no: str) -> str:
    """会话 id 也用确定值，重复运行不会每跑一次多出一条会话。

    取 uuid5 而不是随便拼字符串 —— 这个 id 以后要当 PostgreSQL checkpoint 的
    thread_id 用，形状得和真实会话一致。
    """
    return str(uuid5(NAMESPACE_URL, f"supportflow-demo-conversation-{order_no}"))


def _at(now: datetime, ago: timedelta) -> datetime:
    return now - ago


def _validate() -> None:
    """自检：同一订单不能出现两条演示申请，且申请状态要和订单支付状态对得上。

    第二条尤其重要 —— 如果声明"这条申请已退款完成"，订单就必须真的是 refunded。
    两边不一致的话，演示时会出现"申请显示已退款、订单却还能再申请"这种自相矛盾。
    """
    seen: set[str] = set()
    for spec in DEMO_REFUNDS:
        if spec.order_no in seen:
            raise ValueError(f"同一订单出现两条演示申请：{spec.order_no}")
        seen.add(spec.order_no)

        # 申请已走完退款闭环 → 订单必须已经翻成已退款；否则订单应还是已支付。
        if spec.status is RefundStatus.REFUNDED:
            if spec.record is None or spec.record.status is not RefundExecutionStatus.SUCCEEDED:
                raise ValueError(
                    f"{spec.order_no}: 申请已 refunded，必须配一条 succeeded 的退款流水"
                )
        if spec.status in (RefundStatus.PENDING, RefundStatus.APPROVED, RefundStatus.REJECTED):
            if spec.record is not None and spec.status is RefundStatus.REJECTED:
                raise ValueError(f"{spec.order_no}: 被拒绝的申请不该产生退款流水")

        # 申请时间早于审批时间就是错的（先去申请，才有人批）。
        if spec.approval is not None and spec.approval.decided_ago > spec.created_ago:
            raise ValueError(
                f"{spec.order_no}: 审批时间早于申请时间"
                "（decided_ago 应小于 created_ago）"
            )


async def main() -> None:
    _validate()
    now = utc_now()
    created: list[RefundSpec] = []
    skipped: list[RefundSpec] = []

    try:
        async with SessionLocal() as session:
            async with session.begin():
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
                                [_request_key(s.order_no) for s in DEMO_REFUNDS]
                            )
                        )
                    )
                )

                for spec in DEMO_REFUNDS:
                    if _request_key(spec.order_no) in existing_keys:
                        skipped.append(spec)
                        print(f"Skipped existing refund request: {spec.order_no}")
                        continue

                    order = orders.get(spec.order_no)
                    if order is None:
                        raise RuntimeError(
                            f"Missing demo order: {spec.order_no}; "
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

                    # 退款申请的外键指向会话；真实流程里由 create_refund_request 建，
                    # 这里补一条，标题直接用订单号，方便在库里对上号。
                    conversation_id = _conversation_id(spec.order_no)
                    conversation = await session.get(Conversation, conversation_id)
                    if conversation is None:
                        session.add(
                            Conversation(
                                id=conversation_id,
                                user_id=order.user_id,
                                title=f"退款申请 {spec.order_no}",
                                created_at=_at(now, spec.created_ago),
                                updated_at=_at(now, spec.created_ago),
                            )
                        )

                    request = RefundRequest(
                        request_key=_request_key(spec.order_no),
                        order_id=order.id,
                        conversation_id=conversation_id,
                        # 金额取订单实付，和线上规则一致：请求体里没有金额这个字段。
                        amount_cents=order.paid_amount_cents,
                        reason_original=spec.reason,
                        reason_category=None,
                        status=spec.status,
                        created_at=_at(now, spec.created_ago),
                        updated_at=_at(
                            now,
                            spec.approval.decided_ago
                            if spec.approval is not None
                            else spec.created_ago,
                        ),
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
                                refund_no=_refund_no(spec.order_no),
                                amount_cents=order.paid_amount_cents,
                                status=spec.record.status,
                                attempt_count=spec.record.attempt_count,
                                last_error=spec.record.last_error,
                                succeeded_at=(
                                    None
                                    if spec.record.succeeded_ago is None
                                    else _at(now, spec.record.succeeded_ago)
                                ),
                                created_at=_at(now, spec.record.created_ago),
                                updated_at=_at(now, spec.record.created_ago),
                            )
                        )

                    created.append(spec)

        print(f"Refund requests: created {len(created)}, skipped {len(skipped)}.")
        for spec in created:
            print(
                f"  {_request_key(spec.order_no)} order={spec.order_no} "
                f"status={spec.status.value} reason={spec.reason} | {spec.note}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
