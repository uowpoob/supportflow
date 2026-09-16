"""订单查询。

归属检查、分页、排序都发生在这一层 —— HTTP 路由和第 5 天的 Agent Tool
共用同一套，谁都不许自己拼 SQL。
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

    # 分页要两条 SQL：LIMIT 只给你当前页，翻页按钮还得知道总数。
    # total 从同一个 stmt 派生（.subquery()），过滤条件只写一处 —— 分头写两份
    # 条件，早晚改一处忘一处，总数和列表对不上。
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))

    # 排序必须显式指定：不写的话 MySQL 返回顺序没有任何保证，
    # 翻页时同一行可能出现在两页里，也可能被整页跳过。
    # 第二个键用 id 兜底 —— created_at 精度到微秒，但同一事务里插入的多行
    # 完全可能撞上同一个值，撞了顺序就不稳。
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
