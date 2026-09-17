"""退款查询：申请列表 / 详情、审批记录、退款流水。

另外还住着两个**事务原语**（`_end_transaction` / `_reload`），它们看着跟"查询"不搭，
但语义上正是查询的前置动作："先结束事务，再读，读到的才是最新的"。
`requests.py` 和 `approvals.py` 写完库之后都要靠它们才能把正确的结果返回出去。
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
from supportflow.services.refunds.types import RefundRequestRow, RefundRequestView

# ------------------------------- 事务原语 -------------------------------


async def _end_transaction(db: AsyncSession) -> None:
    """结束当前事务 —— 这个函数看着多余，但少了它就会出现"返回旧数据"的 bug。

    MySQL 默认隔离级别是 REPEATABLE READ，事务的读快照在**事务里第一条普通
    SELECT** 时建立（认证依赖里查 `auth_sessions` / `users` 就已经建立了），
    之后同一条事务里的普通 SELECT 一直看那份旧快照。

    而 `SELECT ... FOR UPDATE` 是**锁定读**，它不看快照，永远读最新已提交版本。
    两者混用就会出现这种非常反直觉的现象：

        SELECT ... FOR UPDATE  -> 看到 refunded（最新）
        随后那条普通 SELECT    -> 看到 pending（旧快照）
        于是响应里返回了"待审批"，而库里明明是"已退款"

    并发批准同一条申请时就是这么炸的：第一个请求改完状态提交，其余九个在锁上排队，
    醒来后正确判定"已经批过了"，走幂等分支 —— 但没结束事务，
    紧接着那次重读又退回旧快照，把 `pending` 写进了响应。

    所以约定一条不变式：**这一层的写函数返回之前，事务一定已经结束**。
    这样调用方（路由、Agent Tool）之后的任何查询都是新事务、新快照。
    """
    await db.commit()


async def _reload(db: AsyncSession, request: RefundRequest) -> RefundRequest:
    """在新事务里把这一行重新读一遍。

    必须在上面的 `_end_transaction` 之后调用 —— 先提交、后重读，才会读到最新值。
    顺序反了就是读到旧快照，`refresh` 反而会把内存里正确的值覆盖成旧值。
    """
    await db.refresh(request)
    return request


# ------------------------------- 申请：列表与详情 -------------------------------


async def _count(db: AsyncSession, stmt) -> int:
    """从同一个 stmt 派生总数 —— 过滤条件只写一处，见 orders.py 的说明。"""
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


# ------------------------------- 审批记录与退款流水 -------------------------------


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
