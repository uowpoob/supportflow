"""订单查询：唯一拼订单 SQL 的地方。

"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import Order, OrderItem, User


async def list_all_orders(
    db: AsyncSession,
    offset: int,
    limit: int,
) -> tuple[list[tuple[Order, str]], int]:
    """全部订单（管理侧），按创建时间倒序，返回 (当前页, 总行数)。

    管理员不做归属过滤 —— 权限在 router 层由 `require_admin` 拦掉了，
    这里再过滤一道没意义（他要看的就是所有人的单）。

    join 出 `users.username` 供界面显示归属：一次查询带上，好过拿 10 个
    `user_id` 回头再查 10 次。
    """
    stmt = select(Order, User.username).join(User, Order.user_id == User.id)

    # 分页要两条 SQL：total 由同一 stmt 派生（.subquery()），过滤条件只写一处，避免分头写对不上。
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))

    # 排序必须显式：否则 MySQL 顺序无保证，翻页会丢行或重复；
    # 第二键用 id 兜底——created_at 可能撞值，撞了顺序不稳。
    rows = (
        await db.execute(
            stmt.order_by(Order.created_at.desc(), Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    return [(row[0], row[1]) for row in rows], int(total or 0)


async def get_order_any(
    db: AsyncSession,
    order_no: str,
) -> tuple[Order, str] | None:
    """按订单号取单个订单（管理侧，不校验归属）；带出归属客户的用户名。"""
    row = (
        await db.execute(
            select(Order, User.username)
            .join(User, Order.user_id == User.id)
            .where(Order.order_no == order_no)
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def list_order_items(db: AsyncSession, order_id: int) -> list[OrderItem]:
    """某订单的全部明细，按插入顺序。

    只按 order_id 查，不带归属条件：调用方必须**先**拿到订单本身
    （也就是先过一遍归属检查），不能拿它当入口。
    """
    items = await db.scalars(
        select(OrderItem).where(OrderItem.order_id == order_id).order_by(OrderItem.id)
    )
    return list(items)


# ------------------------------- 客户侧 -------------------------------


async def list_orders_for_user(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
) -> tuple[list[Order], int]:
    """订单（客户侧），按创建时间倒序，返回 (当前页, 总行数)。

    """
    stmt = select(Order).where(Order.user_id == user_id)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.scalars(
            stmt.order_by(Order.created_at.desc(), Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    return list(rows), int(total or 0)


async def get_order_for_user(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> Order | None:
    """我的某个订单；不是我的、或不存在，都返回 `None`。

    """
    return await db.scalar(
        select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
    )


async def get_order_with_items_for_user(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> tuple[Order, list[OrderItem]] | None:
    """订单详情：归属检查通过后，再取明细。

    """
    order = await get_order_for_user(db, user_id, order_no)
    if order is None:
        return None
    return order, await list_order_items(db, order.id)
