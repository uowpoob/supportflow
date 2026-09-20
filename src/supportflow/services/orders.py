"""订单查询入口。

归属检查、分页、排序的实现都在 `repository/order/queries.py`；这一层只剩一件事：
**让调用方的 import 一行都不用改**。

为什么不让路由和 Agent Tool 直接去 import repository？因为"读也走 services"是这个项目的
约定 —— HTTP 路由、Agent Tool、以后的定时任务都只认 `services/` 这一个入口，
查询换了实现（加缓存、加过滤）时只改这里。

函数签名逐个写出来，**不要**用 `*args / **kwargs` 转发：签名写出来，
编辑器跳转和类型检查才能继续帮上忙。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import Order, OrderItem
from supportflow.repository.order import queries as order_repo


async def list_all_orders(
    db: AsyncSession,
    offset: int,
    limit: int,
) -> tuple[list[tuple[Order, str]], int]:
    """全部订单（管理侧），返回 (当前页, 总行数)。实现见 `repository/order/queries.py`。"""
    return await order_repo.list_all_orders(db, offset, limit)


async def get_order_any(
    db: AsyncSession,
    order_no: str,
) -> tuple[Order, str] | None:
    """按订单号取订单（管理侧，不校验归属）。"""
    return await order_repo.get_order_any(db, order_no)


async def list_order_items(db: AsyncSession, order_id: int) -> list[OrderItem]:
    """某订单的全部明细。调用方必须**先**过一遍归属检查，不能拿它当入口。"""
    return await order_repo.list_order_items(db, order_id)


async def list_orders_for_user(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
) -> tuple[list[Order], int]:
    """**我的**订单（客户侧）。`user_id` 只能来自认证态，绝不能来自请求参数。"""
    return await order_repo.list_orders_for_user(db, user_id, offset, limit)


async def get_order_for_user(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> Order | None:
    """**我的**某个订单；不是我的、或不存在，都是 `None`（两种情况不可区分）。"""
    return await order_repo.get_order_for_user(db, user_id, order_no)


async def get_order_with_items_for_user(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> tuple[Order, list[OrderItem]] | None:
    """**我的**订单详情：归属检查通过后再取明细。"""
    return await order_repo.get_order_with_items_for_user(db, user_id, order_no)
