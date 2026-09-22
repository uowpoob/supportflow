"""会话归属、消息展示和单轮对话；HTTP 不直接操作 checkpoint 或拼接 SQL。"""

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing, asynccontextmanager
from uuid import uuid4

from anyio import CancelScope
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.agent.support_agent import SUPPORT_STREAM_TAG
from supportflow.agents.graph.context import SupportContext
from supportflow.models.entities import Conversation
from supportflow.repository import conversations as conversation_repo
from supportflow.schemas.conversations import (
    ChatMessageOut, ConversationMessagesOut, MessageDeltaOut, MessageStartOut,
    MessageStreamErrorOut, MessageStreamEvent, MessageTurnOut, RetrievedSourceOut,
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

    @asynccontextmanager
    async def stream_message(
        self, db: AsyncSession, user_id: int, conversation_id: str, content: str,
    ) -> AsyncIterator[AsyncIterator[MessageStreamEvent]]:
        """进入时校验并占用会话，退出时关闭图流；由请求级依赖覆盖整个 SSE 生命周期。"""
        await _require_conversation(db, user_id, conversation_id)
        if conversation_id in self._running:
            raise ConversationError("本会话正在回复，请等待本轮完成", status_code=409)
        # 检查与添加之间没有 await；同一事件循环中的请求不会同时进入。
        self._running.add(conversation_id)
        try:
            # 收到新消息即更新最近活动时间，并在等待模型前结束这段 MySQL 事务。
            await conversation_repo.touch_conversation(db, user_id, conversation_id)
            await db.commit()
            message = HumanMessage(id=str(uuid4()), content=content)
            stream = self._stream_reply(db, user_id, conversation_id, message)
            try:
                yield stream
            finally:
                # StreamingResponse 在发送失败时不一定主动关闭迭代器。
                # shield 让断开连接后的清理能结束，再释放占用和请求数据库会话。
                with CancelScope(shield=True):
                    await stream.aclose()
        finally:
            self._running.discard(conversation_id)

    async def _stream_reply(
        self, db: AsyncSession, user_id: int, conversation_id: str, message: HumanMessage,
    ) -> AsyncIterator[MessageStreamEvent]:
        config = {"configurable": {"thread_id": conversation_id}}
        yield "start", MessageStartOut(
            conversation_id=conversation_id,
            message=ChatMessageOut(id=message.id, role="user", content=str(message.text)),
        )
        try:
            # 内部 create_agent 是嵌套图，需要 subgraphs=True 才能收到它的模型片段。
            # v2 统一使用 part["data"]，避免嵌套图改变外层元组结构。
            async with aclosing(self.graph.astream(
                {"messages": [message]}, config,
                context=SupportContext(user_id, conversation_id, db),
                stream_mode="messages", subgraphs=True, version="v2",
            )) as events:
                async for part in events:
                    chunk, metadata = part["data"]
                    if SUPPORT_STREAM_TAG not in metadata.get("tags", []):
                        continue
                    if not isinstance(chunk, AIMessage):
                        continue
                    if chunk.tool_calls or getattr(chunk, "tool_call_chunks", None):
                        continue
                    # text 只提取正文，不转发 reasoning_content、工具参数和元数据。
                    text = str(chunk.text)
                    if text and chunk.id:
                        yield "message", MessageDeltaOut(message_id=chunk.id, delta=text)

            # 流结束后读取已保存的最终状态，不再次调用模型。
            snapshot = await self.graph.aget_state(config)
            state = snapshot.values
            history = state["messages"]
            start = next(i for i, item in enumerate(history) if item.id == message.id)
            yield "done", MessageTurnOut(
                conversation_id=conversation_id,
                messages=_public_messages(history[start:]),
                retrieval_status=state.get("retrieval_status", "not_requested"),
                retrieved_sources=[RetrievedSourceOut(
                    document_id=item["document_id"], chunk_id=item["chunk_id"],
                    title=item["title"], source=item["source"],
                    section=item.get("section"), score=item.get("score"),
                ) for item in state.get("retrieved_documents", [])],
            )
        except Exception as exc:
            # HTTP 流已经开始，只能发送 error 事件；不自动重跑业务。
            # CancelledError / GeneratorExit 不属于 Exception，会继续向外传播。
            logger.warning("对话流执行失败（%s）", type(exc).__name__)
            yield "error", MessageStreamErrorOut(
                message="本轮对话未完成，请先查看历史消息及订单、退款状态后再决定是否重新发送",
            )
