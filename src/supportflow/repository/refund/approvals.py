"""审批相关的写入与加锁读：行锁、审批行、退款流水。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import (
    Order,
    RefundApproval,
    RefundRecord,
    RefundRequest,
)
from supportflow.models.enums import ApprovalDecision, RefundExecutionStatus


async def lock_request_by_key(
    db: AsyncSession,
    request_key: str,
) -> RefundRequest | None:
    """按 `request_key` 取申请，**并锁住这一行**直到事务结束。

    十个并发批准会在这里排队：第一个改完状态，后面九个进来一看已经批准，
    走幂等分支返回 —— 这就是"并发批准只产生一条流水"的实现方式。
    """
    return await db.scalar(
        select(RefundRequest)
        .where(RefundRequest.request_key == request_key)
        .with_for_update()
    )


async def lock_order_by_id(db: AsyncSession, order_id: int) -> Order | None:
    """按主键取订单并锁住 —— 审批时复核金额、避免并发改单用。"""
    return await db.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )


async def insert_approval(
    db: AsyncSession,
    *,
    refund_request_id: int,
    admin_id: int,
    decision: ApprovalDecision,
    comment: str | None,
) -> None:
    """记一条管理员决策（审计凭据）。`admin_id` 只从认证态来，接口上没有这个参数。"""
    db.add(
        RefundApproval(
            refund_request_id=refund_request_id,
            admin_id=admin_id,
            decision=decision,
            comment=comment,
        )
    )


async def insert_record(
    db: AsyncSession,
    *,
    refund_request_id: int,
    refund_no: str,
    amount_cents: int,
    status: RefundExecutionStatus,
    attempt_count: int,
    last_error: str | None,
    succeeded_at: datetime | None,
) -> None:
    """记一条退款执行流水 —— "钱真的动了"的唯一凭据。"""
    db.add(
        RefundRecord(
            refund_request_id=refund_request_id,
            refund_no=refund_no,
            amount_cents=amount_cents,
            status=status,
            attempt_count=attempt_count,
            last_error=last_error,
            succeeded_at=succeeded_at,
        )
    )
