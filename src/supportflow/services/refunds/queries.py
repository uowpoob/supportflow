"""退款读操作入口：申请列表 / 详情、审批记录、退款流水。

SQL 全部在 `repository/refund/queries.py`，这里只是转发 —— 保持这个入口不变，
HTTP 路由和 Agent Tool 的 import 就一行都不用改。

⚠️ 两个**事务原语**（`_end_transaction` / `_reload`）不在这里了，搬到了
`repository/refund/transaction.py`。它们不是"查询"，而是写完之后必须做的一次收尾
（先提交、再重读，否则会返回旧快照）—— 所以 `requests.py` / `approvals.py`
从那边 import，别在这儿找。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.enums import RefundStatus
from supportflow.repository.refund import queries as refund_queries
from supportflow.repository.refund.types import RefundRequestRow, RefundRequestView


async def list_refund_requests_for_user(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
    status: RefundStatus | None = None,
) -> tuple[list[RefundRequestRow], int]:
    """**我的**退款申请，按提交时间倒序。归属条件是一条内连接。"""
    return await refund_queries.list_refund_requests_for_user(
        db, user_id, offset, limit, status
    )


async def list_all_refund_requests(
    db: AsyncSession,
    offset: int,
    limit: int,
    status: RefundStatus | None = None,
) -> tuple[list[RefundRequestRow], int]:
    """全部退款申请（管理侧待办队列）。"""
    return await refund_queries.list_all_refund_requests(db, offset, limit, status)


async def get_refund_request_for_user(
    db: AsyncSession,
    user_id: int,
    request_key: str,
) -> RefundRequestView | None:
    """**我的**某条申请。别人的申请查出来就是 `None`。"""
    return await refund_queries.get_refund_request_for_user(db, user_id, request_key)


async def get_refund_request_any(
    db: AsyncSession,
    request_key: str,
) -> RefundRequestView | None:
    """管理侧详情：不校验归属（管理员要看的就是所有人的申请）。"""
    return await refund_queries.get_refund_request_any(db, request_key)


async def list_refund_approvals(
    db: AsyncSession,
    offset: int,
    limit: int,
) -> tuple[list[tuple[object, str, str, str]], int]:
    """审批记录（审计用）：只有被决策过的申请才会有行。"""
    return await refund_queries.list_refund_approvals(db, offset, limit)


async def list_refund_records(
    db: AsyncSession,
    offset: int,
    limit: int,
) -> tuple[list[tuple[object, str, str]], int]:
    """退款执行流水：`refund_no` / `attempt_count` / `last_error` / `succeeded_at`。"""
    return await refund_queries.list_refund_records(db, offset, limit)
