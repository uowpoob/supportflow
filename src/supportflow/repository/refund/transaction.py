"""两个事务原语：结束当前事务 + 在新事务里重读那一行。

它们看着跟"查库"不搭，但语义上正是查询的前置动作："先结束事务，再读，
读到的才是最新的"。`services/refunds/requests.py` 和 `approvals.py` 写完库之后
都要靠它们才能把正确的结果返回出去。

放在 repository 里，是因为 `commit` / `refresh` 是本层唯一允许碰的事务收尾动作；
**什么时候**调用它们仍然是业务决策，由 `services/refunds/` 决定。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import RefundRequest


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


async def _rollback(db: AsyncSession) -> None:
    """回滚当前事务。

    只在一种情况下用：提交时撞上了唯一约束（两个请求同时通过了资格判定）。
    回滚之后必须先重新读一次再提交 —— 否则会话里那些没写成功的对象还挂着，
    下一次 flush 会再次撞约束。
    """
    await db.rollback()
