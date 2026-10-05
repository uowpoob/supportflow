"""客户会话的数据访问；归属过滤在 SQL 中完成，事务由服务层管理。"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.db.base import utc_now
from supportflow.models.entities import Conversation


async def create_conversation(
    db: AsyncSession,
    user_id: int,
    title: str,
) -> Conversation:
    """新建会话并取得 ORM 默认生成的 UUID，不提交事务。"""
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    await db.flush()
    return conversation


async def list_conversations_for_user(
    db: AsyncSession,
    user_id: int,
    offset: int,
    limit: int,
) -> tuple[list[Conversation], int]:
    """按最近更新时间倒序返回当前用户的会话和总数。"""
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.scalars(
            stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return list(rows), int(total or 0)


async def get_conversation_for_user(
    db: AsyncSession,
    user_id: int,
    conversation_id: str,
) -> Conversation | None:
    """不存在和不属于当前用户均返回 None。"""
    return await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )


async def touch_conversation(
    db: AsyncSession,
    user_id: int,
    conversation_id: str,
) -> None:
    """更新当前用户会话的活动时间，不提交事务。"""
    await db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .values(updated_at=utc_now())
    )


async def update_title(
    db: AsyncSession,
    user_id: int,
    conversation_id: str,
    title: str,
) -> None:
    """更新当前用户会话的标题，不提交事务。"""
    await db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .values(title=title)
    )
