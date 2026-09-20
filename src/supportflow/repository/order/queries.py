"""订单查询：唯一拼订单 SQL 的地方。

归属检查、分页、排序都发生在这里 —— HTTP 路由和 Agent Tool 共用同一套，
谁都不许自己拼 SQL。本层不判断业务：能看哪一单、该不该拒绝，由
`services/orders.py` 和路由层决定。
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


# ------------------------------- 客户侧 -------------------------------
#
# 这一组函数跟上面那组只差一个 `Order.user_id == user_id`，但**必须分开写**。
# 千万不要图省事搞成 `user_id: int | None = None`，传 None 就不过滤 ——
# 那种签名早晚会有人（包括 Agent）传错一次，把客户查询悄悄降级成"全表"。
# 两个名字摆在这儿，用错了一眼就能看出来。


async def list_orders_for_user(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
) -> tuple[list[Order], int]:
    """**我的**订单（客户侧），按创建时间倒序，返回 (当前页, 总行数)。

    `user_id` 只能来自认证态（`get_current_user` 查出来的那个 User），
    绝不能来自请求参数 —— 那是越权的入口。
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
    """**我的**某个订单；不是我的、或不存在，都返回 `None`。

    归属检查就在这一个 `where` 里 —— 这是有意为之，别改成"先查出来再 if 比对"：

        order = await get_order_any(db, order_no)
        if order.user_id != user_id:        # ← 一旦这么写，就多出一条代码路径
            raise HTTPException(403, "无权访问该订单")

    那样写的后果是"订单存在但不是我的"和"订单不存在"变成两种不同响应，
    等于告诉对方这个订单号是真的 —— 可以拿去枚举。塞进同一个 where，
    两种情况天然都得到 `None`，调用方再统一转成同一个 404 即可。
    """
    return await db.scalar(
        select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
    )


async def get_order_with_items_for_user(
    db: AsyncSession,
    user_id: int,
    order_no: str,
) -> tuple[Order, list[OrderItem]] | None:
    """**我的**订单详情：归属检查通过后，再取明细。

    两次查询而不是一次 join：`Order` 与 `OrderItem` 之间没有配 `relationship`，
    异步场景下懒加载会直接抛 `MissingGreenlet`（同步代码里看不出来这个坑）。
    先查订单还有一层好处 —— 归属不通过就直接返回，明细那条 SQL 根本不会发。
    """
    order = await get_order_for_user(db, user_id, order_no)
    if order is None:
        return None
    return order, await list_order_items(db, order.id)
