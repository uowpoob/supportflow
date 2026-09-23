"""会话归属、消息展示和单轮对话；HTTP 不直接操作 checkpoint 或拼接 SQL。"""

import logging
from collections.abc import Sequence
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.graph.context import SupportContext
from supportflow.models.entities import Conversation
from supportflow.repository import conversations as conversation_repo
from supportflow.schemas.conversations import (
    ChatMessageOut, ConversationMessagesOut, MessageTurnOut, RetrievedSourceOut,
)

logger = logging.getLogger(__name__)


class ConversationError(Exception):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def create_conversation(db: AsyncSession, user_id: int, title: str) -> Conversation:
    """先提交 MySQL 会话，后续消息才可以使用它的 UUID 作为 thread_id。"""
    try:
        conversation = await conversation_repo.create_conversation(db, user_id, title)
        await db.commit()
        return conversation
    except Exception:
        await db.rollback()
        raise


async def list_conversations_for_user(
    db: AsyncSession, user_id: int, offset: int, limit: int,
) -> tuple[list[Conversation], int]:
    return await conversation_repo.list_conversations_for_user(db, user_id, offset, limit)


async def _require_conversation(db: AsyncSession, user_id: int, conversation_id: str) -> None:
    # 归属与 ID 写在同一个查询里：别人的会话和不存在的会话统一 404。
    if await conversation_repo.get_conversation_for_user(db, user_id, conversation_id) is None:
        raise ConversationError("会话不存在", status_code=404)


def _public_messages(messages: Sequence[BaseMessage]) -> list[ChatMessageOut]:
    """只输出用户文字与助手答复，不暴露系统提示、工具参数、工具返回或推理块。"""
    visible = []
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage) and not message.tool_calls:
            role = "assistant"
        else:
            continue
        content = str(message.text)
        if content:
            visible.append(ChatMessageOut(
                id=message.id or f"history-{index}", role=role, content=content,
            ))
    return visible


class ConversationChat:
    """每个服务进程复用图；数据库会话和身份由每次请求单独提供。"""

    def __init__(self, graph: CompiledStateGraph) -> None:
        self.graph = graph
        # 最小的单进程并发保护；多进程锁与请求重试幂等留给运行状态模块。
        self._running: set[str] = set()

    async def list_messages(
        self, db: AsyncSession, user_id: int, conversation_id: str, offset: int, limit: int,
    ) -> ConversationMessagesOut:
        await _require_conversation(db, user_id, conversation_id)
        # 结束认证/归属查询的只读事务，再读取 PostgreSQL checkpoint。
        await db.commit()
        try:
            snapshot = await self.graph.aget_state({"configurable": {"thread_id": conversation_id}})
        except Exception as exc:
            logger.warning("读取会话历史失败（%s）", type(exc).__name__)
            raise ConversationError("会话历史暂不可用", status_code=503) from exc
        messages = _public_messages(snapshot.values.get("messages", []))
        return ConversationMessagesOut(
            conversation_id=conversation_id, items=messages[offset:offset + limit],
            total=len(messages), offset=offset, limit=limit,
        )

    async def send_message(
        self, db: AsyncSession, user_id: int, conversation_id: str, content: str,
    ) -> MessageTurnOut:
        await _require_conversation(db, user_id, conversation_id)
        if conversation_id in self._running:
            raise ConversationError("本会话正在回复，请等待本轮完成", status_code=409)
        # 检查与添加之间没有 await；同一事件循环中的请求不会同时进入。
        self._running.add(conversation_id)
        try:
            config = {"configurable": {"thread_id": conversation_id}}
            snapshot = await self.graph.aget_state(config)
            if snapshot.values.get("pending_approval"):
                raise ConversationError("本会话正在等待管理员审批", status_code=409)
            # 收到新消息即更新最近活动时间，并在等待模型前结束这段 MySQL 事务。
            await conversation_repo.touch_conversation(db, user_id, conversation_id)
            await db.commit()
            message = HumanMessage(id=str(uuid4()), content=content)
            try:
                state = await self.graph.ainvoke(
                    {"messages": [message]},
                    config,
                    context=SupportContext(user_id, conversation_id, db),
                )
                history = state["messages"]
                # 用本轮用户消息 ID 定位增量，避免向前端重复返回整份历史。
                start = next(i for i, item in enumerate(history) if item.id == message.id)
                return MessageTurnOut(
                    conversation_id=conversation_id,
                    messages=_public_messages(history[start:]),
                    status="waiting_approval" if state.get("pending_approval") else "completed",
                    pending_request_key=state.get("pending_approval"),
                    retrieval_status=state.get("retrieval_status", "not_requested"),
                    retrieved_sources=[RetrievedSourceOut(
                        document_id=item["document_id"], chunk_id=item["chunk_id"],
                        title=item["title"], source=item["source"],
                        section=item.get("section"), score=item.get("score"),
                    ) for item in state.get("retrieved_documents", [])],
                )
            except Exception as exc:
                # 不自动重跑：此前的工具可能已经提交了业务写入。
                logger.warning("对话执行失败（%s）", type(exc).__name__)
                raise ConversationError(
                    "本轮对话未完成，请先查看历史消息及订单、退款状态后再决定是否重新发送",
                    status_code=502,
                ) from exc
        finally:
            self._running.discard(conversation_id)

    async def resume_approval(
        self, db: AsyncSession, user_id: int, conversation_id: str, request_key: str,
    ) -> bool:
        """审批事务提交后恢复暂停图；重复调用或表单申请可安全跳过。"""
        if conversation_id in self._running:
            raise ConversationError("本会话正在执行，请稍后重试恢复", status_code=409)
        self._running.add(conversation_id)
        try:
            config = {"configurable": {"thread_id": conversation_id}}
            snapshot = await self.graph.aget_state(config)
            if snapshot.values.get("pending_approval") != request_key:
                return False
            if "wait_for_approval" not in snapshot.next:
                raise ConversationError("审批节点尚未暂停，请稍后重试恢复", status_code=409)
            await self.graph.ainvoke(
                Command(resume={"request_key": request_key}),
                config,
                context=SupportContext(user_id, conversation_id, db),
            )
            return True
        finally:
            self._running.discard(conversation_id)
