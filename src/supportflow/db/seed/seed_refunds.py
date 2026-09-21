"""创建本地演示退款数据：python -m supportflow.db.seed.seed_refunds。

前提：先跑过 python -m supportflow.db.seed.seed_users 和 seed_orders
（本模块按 order_no 找订单，金额也直接取自订单实付）。

为什么订单之外还要单独一个种子：退款申请的状态**不可能**只靠 orders 表造出来。
`evaluate_eligibility` 里有三个分支（已有申请 / 已批准 / 已退款）必须库里真的存在
一条申请才会命中，管理侧的"待办、审批记录、退款流水"三个页面也一样 ——
不灌这些数据，这些页面在演示时永远是空的，看起来就像没做完。

和 seed_orders 一样守两条约束：
1. 可重复运行 —— `request_key` 是写死的 `40992851773300NN`，已存在就跳过。
2. 时间字段相对当前时间算，并且**必须晚于该订单的签收时间** ——
   签收之前不可能发起退款申请，这条也有自检。

金额一律取 `orders.paid_amount_cents`，和线上 `create_refund_request` 的规则一致 ——
演示数据也不该走一条"可以手填金额"的旁路，否则测出来的东西和线上不是一回事。

## 覆盖面

12 条申请把四个人生阶段和两个执行结果铺满（括号里是申请状态 / 执行状态）：

    待审批 3 条 ──── R04 C1-15、R06 C2-02、R10 C2-08
                      → 管理侧"待办"页有东西可批，客户侧显示"待审批"
    已批准 3 条 ──── R02 C1-11、R07 C2-03（processing 打款中）
                      R09 C2-05（succeeded 已打款）
    已拒绝 3 条 ──── R05 C1-12、R08 C2-04、R12 C2-10
                      → 名额已释放：前两单**仍然可以再次申请**（判定为 ok），
                        最后一单本身已超期（判定为 window_expired）
    已退款 3 条 ──── R01 C1-04、R03 C1-14、R11 C2-11
                      → 完整闭环，对应订单支付状态已翻成 refunded

审批记录 9 条（待审批的 3 条还没有审批），退款流水 6 条（只有已批准/已退款才有）。
**没有 failed 流水**：演示库不放"打款失败"这类异常状态，失败重试由单元测试覆盖。

## 编号规则

- `request_key`：16 位纯数字，号段 `409928517733` + 4 位序号，例如 `4099285177330001`。
- `refund_no`：16 位纯数字，号段 `711845902664` + 序号，后 4 位与申请号一致（流水由申请派生）。
- `RefundSpec.label`：人看的短名，只用于注释和打印，不落库。

⚠️ 线上 `services/refunds/requests.py` 里 `request_key` / `refund_no` 都是 `uuid4()`。
演示库用可读的号段只是为了让界面好看，两者的**唯一性要求是一样的**；
真要统一，改的应该是线上那两个生成点，而不是把演示数据改成 UUID。
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
    # ------------------------------ 已退款：完整闭环（3 条） ------------------------------
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
        note="完整闭环（大额笔记本 5499.00 元），订单已退款",
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
    # ------------------------------ 已批准：打款中 / 已打款（3 条） ------------------------------
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
        status=RefundStatus.APPROVED,
        reason="吸盘固定不住，过减速带就掉",
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
        note="已批准、打款成功：覆盖 succeeded 状态（申请仍是 approved）",
    ),
    # ------------------------------ 待审批：管理侧待办（3 条） ------------------------------
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
    # ------------------------------ 已拒绝：名额已释放（3 条） ------------------------------
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
        reason="腕托有异味，闻着不舒服",
        created_ago=timedelta(days=5),
        approval=ApprovalSpec(
            decision=ApprovalDecision.REJECTED,
            comment="经核实非商品质量问题，不符合退款条件",
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
            comment="已超过签收后 14 天退款期限，不予受理",
            decided_ago=timedelta(days=13),
        ),
        note="超期后提交、被拒绝：单子本身超期（判定仍是 window_expired）",
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
        if spec.status is RefundStatus.PENDING and spec.approval is not None:
            raise ValueError(f"{spec.order_no}: 还是待审批，不该有审批记录")

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

        # 已批准的申请必须已经产生了流水（打款中或已打款）。
        if spec.status is RefundStatus.APPROVED and spec.record is None:
            raise ValueError(f"{spec.order_no}: 已批准就该有退款流水（processing 或 succeeded）")

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

                    # 退款申请的外键指向会话；真实流程里由 create_refund_request 建，
                    # 这里补一条，标题直接用订单号，方便在库里对上号。
                    conversation_id = _conversation_id(spec.order_no)
                    conversation = await session.get(Conversation, conversation_id)
                    if conversation is None:
                        session.add(
                            Conversation(
                                id=conversation_id,
                                user_id=order.user_id,
                                title=f"订单 {spec.order_no} 售后咨询",
                                created_at=_at(now, spec.created_ago),
                                updated_at=_at(now, spec.created_ago),
                            )
                        )

                    request = RefundRequest(
                        request_key=_request_key(spec.key_no),
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
                                updated_at=_at(now, spec.record.created_ago),
                            )
                        )

                    created.append(spec)

        approvals = sum(1 for spec in created if spec.approval is not None)
        records = sum(1 for spec in created if spec.record is not None)
        print(
            f"Refund requests: created {len(created)}, skipped {len(skipped)}; "
            f"{approvals} approval(s), {records} record(s)."
        )
        for spec in created:
            print(
                f"  {spec.label} request_key={_request_key(spec.key_no)} "
                f"order={spec.order_no} status={spec.status.value} "
                f"reason={spec.reason} | {spec.note}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
