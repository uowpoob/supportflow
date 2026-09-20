"""退款查询：申请列表 / 详情、审批记录、退款流水。

事务原语（结束事务、重读）在 `transaction.py`，不在这里 —— 它们跟"查询"看着不搭，
单独放一个文件更好找，也免得这个文件的读者以为它们只是两个工具函数。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import (
    Order,
    RefundApproval,
    RefundRecord,
    RefundRequest,
    User,
)
from supportflow.models.enums import RefundStatus
from supportflow.repository.refund.types import RefundRequestRow, RefundRequestView


async def _count(db: AsyncSession, stmt) -> int:
    """从同一个 stmt 派生总数 —— 过滤条件只写一处，见 `order/queries.py` 的说明。"""
    return int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _request_filters(stmt, status: RefundStatus | None):
    return stmt if status is None else stmt.where(RefundRequest.status == status)


async def list_refund_requests_for_user(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
    status: RefundStatus | None = None,
) -> tuple[list[RefundRequestRow], int]:
    """**我的**退款申请，按提交时间倒序。归属条件是一条内连接。"""
    stmt = (
        select(RefundRequest, Order.order_no)
        .join(Order, RefundRequest.order_id == Order.id)
        .where(Order.user_id == user_id)
    )
    stmt = _request_filters(stmt, status)

    total = await _count(db, stmt)
    rows = (
        await db.execute(
            stmt.order_by(RefundRequest.created_at.desc(), RefundRequest.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [RefundRequestRow(request=row[0], order_no=row[1]) for row in rows], total


async def list_all_refund_requests(
    db: AsyncSession,
    offset: int,
    limit: int,
    status: RefundStatus | None = None,
) -> tuple[list[RefundRequestRow], int]:
    """全部退款申请（管理侧待办队列）。带出归属客户，管理员不用自己去对账号表。"""
    stmt = (
        select(RefundRequest, Order.order_no, Order.user_id, User.username)
        .join(Order, RefundRequest.order_id == Order.id)
        .join(User, Order.user_id == User.id)
    )
    stmt = _request_filters(stmt, status)

    total = await _count(db, stmt)
    rows = (
        await db.execute(
            stmt.order_by(RefundRequest.created_at.desc(), RefundRequest.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        RefundRequestRow(request=row[0], order_no=row[1], user_id=row[2], username=row[3])
        for row in rows
    ], total


async def _load_view(db: AsyncSession, request: RefundRequest, username: str | None) -> RefundRequestView:
    order = await db.scalar(select(Order).where(Order.id == request.order_id))
    # 审批行连一次 `users`，把审批人名字一起带出来 —— 界面上只显示一个 admin_id
    # 等于让管理员自己去查账号表，审计信息该自己带着走。
    approval_row = (
        await db.execute(
            select(RefundApproval, User.username)
            .join(User, RefundApproval.admin_id == User.id)
            .where(RefundApproval.refund_request_id == request.id)
        )
    ).first()
    record = await db.scalar(
        select(RefundRecord).where(RefundRecord.refund_request_id == request.id)
    )
    assert order is not None  # 外键 RESTRICT 保证它一定在
    return RefundRequestView(
        request=request,
        order=order,
        username=username,
        approval=None if approval_row is None else approval_row[0],
        approval_admin=None if approval_row is None else approval_row[1],
        record=record,
    )


async def get_refund_request_for_user(
    db: AsyncSession,
    user_id: int,
    request_key: str,
) -> RefundRequestView | None:
    """**我的**某条申请。归属条件在内连接里，别人的申请查出来就是 None。"""
    row = (
        await db.execute(
            select(RefundRequest, Order.order_no)
            .join(Order, RefundRequest.order_id == Order.id)
            .where(RefundRequest.request_key == request_key, Order.user_id == user_id)
        )
    ).first()
    if row is None:
        return None
    return await _load_view(db, row[0], username=None)


async def get_refund_request_any(
    db: AsyncSession,
    request_key: str,
) -> RefundRequestView | None:
    """管理侧详情：不校验归属（管理员要看的就是所有人的申请）。"""
    row = (
        await db.execute(
            select(RefundRequest, Order.order_no, User.username)
            .join(Order, RefundRequest.order_id == Order.id)
            .join(User, Order.user_id == User.id)
            .where(RefundRequest.request_key == request_key)
        )
    ).first()
    if row is None:
        return None
    return await _load_view(db, row[0], username=row[2])


async def list_refund_approvals(
    db: AsyncSession,
    offset: int,
    limit: int,
) -> tuple[list[tuple[RefundApproval, str, str, str]], int]:
    """审批记录（审计用）：申请号、订单号、审批人、决策、意见、时间。

    只有被决策过的申请才会有行 —— "待办列表"要去查 `refund_requests.status='pending'`，
    拿这张表当待办用会永远查出空数组。
    """
    stmt = (
        select(RefundApproval, RefundRequest.request_key, Order.order_no, User.username)
        .join(RefundRequest, RefundApproval.refund_request_id == RefundRequest.id)
        .join(Order, RefundRequest.order_id == Order.id)
        .join(User, RefundApproval.admin_id == User.id)
    )
    total = await _count(db, stmt)
    rows = (
        await db.execute(
            stmt.order_by(RefundApproval.created_at.desc(), RefundApproval.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows], total


async def list_refund_records(
    db: AsyncSession,
    offset: int,
    limit: int,
) -> tuple[list[tuple[RefundRecord, str, str]], int]:
    """退款执行流水：`refund_no` / `attempt_count` / `last_error` / `succeeded_at`。"""
    stmt = (
        select(RefundRecord, RefundRequest.request_key, Order.order_no)
        .join(RefundRequest, RefundRecord.refund_request_id == RefundRequest.id)
        .join(Order, RefundRequest.order_id == Order.id)
    )
    total = await _count(db, stmt)
    rows = (
        await db.execute(
            stmt.order_by(RefundRecord.created_at.desc(), RefundRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [(row[0], row[1], row[2]) for row in rows], total
