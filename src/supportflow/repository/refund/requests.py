"""退款写入：解析/新建会话、把申请行放进会话。

**事务边界不在这里。** `commit` / `rollback`、以及并发撞上唯一约束之后怎么兜底，
全部由 `services/refunds/requests.py` 决定 —— 那是业务策略（"重复提交要幂等"），
不是数据访问。本层只负责把对象挂到会话上，必要时 flush 拿到自增 id。

`insert_refund_request` 里不写 `request_key` / `amount_cents` / `status` 这些字段的值：
值从哪来（服务端生成？取库里实付？）是业务决策，由调用方组装好对象传进来。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.models.entities import Conversation, RefundRequest


async def find_conversation_for_user(
    db: AsyncSession,
    user_id: int,
    conversation_id: str,
) -> Conversation | None:
    """取这条会话，**前提是它属于这个用户**。

    归属检查同样塞进 `where`，查不到就当作不存在 —— 不能把申请挂到别人的会话上，
    也不能因此泄露"这个会话 id 是有效的"。
    """
    return await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )


async def create_conversation(
    db: AsyncSession,
    user_id: int,
    title: str,
) -> Conversation:
    """新建一条会话，并 `flush` 拿到自增 id。

    `conversations.id` 同时是 LangGraph checkpoint 的 `thread_id`，
    所以申请一提交就必须挂在一条真实会话上（`conversation_id` 是 NOT NULL 外键）。

    这里只 flush 不 commit：还没提交，失败一起回滚 —— 不能出现"会话建好了、
    申请没建成"的孤儿会话。
    """
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    await db.flush()
    return conversation


async def insert_refund_request(db: AsyncSession, request: RefundRequest) -> None:
    """把组装好的申请放进会话；提交由调用方决定。"""
    db.add(request)
