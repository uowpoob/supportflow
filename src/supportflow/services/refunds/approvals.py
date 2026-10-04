"""人工审批与模拟退款：行锁串行化、相同决策幂等、执行前复核。

"批准"和"退款"在同一个事务里完成，不允许出现"批准了但没退款"的中间态。

SQL 在 `repository/refund/approvals.py`（带行锁的那两条也是），事务原语在
`repository/refund/transaction.py`；这一层保留的是**决策规则**：
什么情况算重复、什么情况该报 409、执行前要不要复核。
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.models.entities import RefundRequest
from supportflow.models.enums import (
    ApprovalDecision,
    PaymentStatus,
    RefundExecutionStatus,
    RefundStatus,
)
from supportflow.repository.refund import approvals as approval_repo
from supportflow.repository.refund.transaction import _end_transaction, _reload
from supportflow.services.refunds.errors import RefundError


async def decide_refund_request(
    db: AsyncSession,
    admin_id: int,
    request_key: str,
    decision: ApprovalDecision,
    comment: str | None,
) -> RefundRequest:
    """管理员批准或拒绝；**批准即执行模拟退款**，两者在同一个事务里。

    整段包在一个事务里：`refund_requests` 改状态、插 `refund_approvals`、
    插 `refund_records`、改 `orders.payment_status` 要么全成，要么全不成。
    "模拟退款"只是写一行记录加改两个字段，没有外部系统，不存在
    "钱退了但状态没改"的中间窗口。
    """
    # 本查询带 `SELECT ... FOR UPDATE` 行锁：并发批准在此串行化，
    # 已批准的走幂等分支返回，从而"并发批准只产生一条流水"。
    request = await approval_repo.lock_request_by_key(db, request_key)
    if request is None:
        raise RefundError("request_not_found", "退款申请不存在", status_code=404)

    already_approved = request.status in (RefundStatus.APPROVED, RefundStatus.REFUNDED)
    already_rejected = request.status is RefundStatus.REJECTED
    want_approve = decision is ApprovalDecision.APPROVED

    if already_approved or already_rejected:
        same_decision = already_approved == want_approve
        if not same_decision:
            raise RefundError(
                "already_decided",
                f"该申请已被处理为「{'批准' if already_approved else '拒绝'}」，不能改成其他结果",
            )
        # 决策相同 → 幂等返回。但必须结束事务再重读：本次 `FOR UPDATE` 未提交，
        # 不重读则调用方拿到旧快照（详见 repository/refund/transaction.py 的长注释）。
        await _end_transaction(db)
        return await _reload(db, request)

    await approval_repo.insert_approval(
        db,
        refund_request_id=request.id,
        # admin_id 只从认证态来 —— 接口上没有这个参数，伪造不了。
        admin_id=admin_id,
        decision=decision,
        comment=comment,
    )

    if not want_approve:
        request.status = RefundStatus.REJECTED
        await _end_transaction(db)
        return await _reload(db, request)

    # 先推到 approved（事务内中间态，外部看不到）：保留这一步便于接入真实支付时拆成独立事务。
    request.status = RefundStatus.APPROVED
    await _execute_mock_refund(db, request)

    await _end_transaction(db)
    return await _reload(db, request)


async def _execute_mock_refund(db: AsyncSession, request: RefundRequest) -> None:
    """模拟退款：写一条执行流水，把订单标成已退款，申请标成已退款。

    执行前**重新复核一遍**（验收用例 E11）：从申请提交到管理员点批准之间，
    订单金额可能被改、可能已经别处退过款。审批人点的是"批准这条申请"，
    不是"无条件给钱" —— 依据变了就该拦下来，而不是照旧执行。
    """
    order = await approval_repo.lock_order_by_id(db, request.order_id)
    if order is None:
        raise RefundError("order_not_found", "订单不存在", status_code=404)

    if order.payment_status is PaymentStatus.REFUNDED:
        raise RefundError("order_refunded", "该订单已经退款完成，不能重复退款")
    if order.payment_status is not PaymentStatus.PAID:
        raise RefundError("order_unpaid", "订单当前不是已支付状态，不能退款")
    if order.paid_amount_cents != request.amount_cents:
        # 金额对不上说明订单被改过，宁可失败也不能按旧金额退（多退少退都是事故）。
        raise RefundError(
            "amount_changed",
            "订单实付金额已变化，与申请金额不一致，请人工核对后再处理",
        )

    await approval_repo.insert_record(
        db,
        refund_request_id=request.id,
        refund_no=str(uuid4()),
        amount_cents=request.amount_cents,
        status=RefundExecutionStatus.SUCCEEDED,
        attempt_count=1,
        last_error=None,
        succeeded_at=utc_now(),
    )
    order.payment_status = PaymentStatus.REFUNDED
    request.status = RefundStatus.REFUNDED
