"""两个事务原语：结束当前事务 + 在新事务里重读那一行。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import RefundRequest


async def _end_transaction(db: AsyncSession) -> None:
    """结束当前事务 —— 这个函数看着多余，但少了它就会出现"返回旧数据"的 bug。

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
