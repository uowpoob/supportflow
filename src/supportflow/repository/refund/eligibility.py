"""退款的两个基础查询：按订单号取订单、按状态集取"占名额"的申请。

只提供**通用**查询，不固化规则 —— 哪些状态算"占名额"由
`services/refunds/types.py` 的 `ACTIVE_REQUEST_STATUSES` 决定，调用时传进来。
一旦本层自己写死那个状态集合，规则就变成住在两个地方了，
而"改一处忘一处"正是退款域最怕的那类 bug。
"""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import Order, RefundRequest
from supportflow.models.enums import RefundStatus


async def find_order_for_user(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> Order | None:
    """按订单号取订单，归属条件写在**同一个 where** 里。

    订单不存在、或存在但不是这个用户的，都返回 `None` —— 两种情况天然同一条路径，
    调用方无从区分，也就无从拿它探测"某个订单号是否真实存在"。
    """
    return await db.scalar(
        select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
    )


async def find_request_in_statuses(
    db: AsyncSession,
    order_id: int,
    statuses: Collection[RefundStatus],
) -> RefundRequest | None:
    """该订单当前那条处于 `statuses` 里的申请，没有就是 `None`。

    数据库有 `refund_requests.active_order_id` 唯一约束保证最多一条，
    所以这里不需要 ORDER BY —— 真要查出两行，那是约束被人删了，属于该炸的情况。
    """
    return await db.scalar(
        select(RefundRequest).where(
            RefundRequest.order_id == order_id,
            RefundRequest.status.in_(statuses),
        )
    )
