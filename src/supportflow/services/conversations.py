"""会话归属、消息展示和单轮对话；HTTP 不直接操作 checkpoint 或拼接 SQL。"""

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.graph.context import SupportContext
from supportflow.agents.llm import chat_model
from supportflow.agents.graph.state import SupportState
from supportflow.db.session import SessionLocal
from supportflow.models.entities import Conversation
from supportflow.repository import conversations as conversation_repo
from supportflow.repository import refund as refund_repo
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


def _turn_from_state(
    state: SupportState, conversation_id: str, message_id: str, title: str | None = None,
) -> MessageTurnOut:
    """从本轮用户消息开始提取结果，供普通请求和流式请求共用。"""
    history = state["messages"]
    start = next(i for i, item in enumerate(history) if item.id == message_id)
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
        title=title,
    )


class ConversationChat:
    """每个服务进程复用图；数据库会话和身份由每次请求单独提供。"""

    def __init__(self, graph: CompiledStateGraph) -> None:
        self.graph = graph
        # 最小的单进程并发保护；多进程锁与请求重试幂等留给运行状态模块。
        self._running: set[str] = set()

    async def _generate_title(self, user_message: str) -> str | None:
        """用模型把首轮对话概括成一句短标题；失败时返回 None，不影响本轮结果。"""
        prompt = (
            "把下面这句售后咨询概括成一个不超过 20 个字的标题，"
            "直接输出标题本身，不要引号、不要句号、不要额外解释。\n\n"
            f"客户：{user_message}"
        )
        try:
            response = await chat_model.ainvoke([SystemMessage(content=prompt)])
        except Exception as exc:
            logger.warning("生成会话标题失败（%s）", type(exc).__name__)
            return None
        title = str(response.content).strip().strip('"').strip("“”").strip()
        if not title:
            return None
        return title[:50]

    async def _maybe_generate_title(
        self, db: AsyncSession, user_id: int, conversation_id: str, user_message: str,
        was_empty: bool,
    ) -> str | None:
        """首轮结束后自动生成标题；不是首轮或当前标题已被改过时跳过。

        判断依据：本轮开始前 checkpoint 里还没有任何消息（`was_empty`），且 MySQL 里
        标题仍是默认的「新会话」。这样既能限定在「首轮」，又不会覆盖用户或之前轮次
        已经生成的标题。
        """
        if not was_empty:
            return None
        conversation = await conversation_repo.get_conversation_for_user(db, user_id, conversation_id)
        if conversation is None or conversation.title != "新会话":
            return None
        title = await self._generate_title(user_message)
        if title is None:
            return None
        try:
            await conversation_repo.update_title(db, user_id, conversation_id, title)
            await db.commit()
        except Exception:
            await db.rollback()
            return None
        return title

    async def delete_conversation(self, db: AsyncSession, user_id: int, conversation_id: str) -> None:
        """删除会话：先清退款链、再删会话行，最后删 PostgreSQL checkpoint。

        归属校验放在最前面 —— 别人的会话和不存在的会话统一 404，不泄露"id 是否有效"。
        删除顺序：
        1. 挂在会话上的退款申请（及其审批、流水）—— `conversation_id` 是 RESTRICT 外键，
           不先清掉就删不掉会话；
        2. 会话行本身（MySQL）；
        3. PostgreSQL 里这条 thread 的 checkpoint（`adelete_thread` 删三张表）。
        MySQL 与 PG 是两个库、没有跨库事务：先删 MySQL 并提交，再删 PG；
        PG 那步失败只影响历史记忆的清理，会话本体已删，不会留下"删不掉的会话"。
        """
        await _require_conversation(db, user_id, conversation_id)
        if conversation_id in self._running:
            raise ConversationError("本会话正在回复，请等待本轮完成后再删除", status_code=409)
        try:
            await refund_repo.delete_requests_for_conversation(db, conversation_id)
            deleted = await conversation_repo.delete_conversation(db, user_id, conversation_id)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        # 上面 _require_conversation 已经确认存在，这里 deleted 理应为 True；留个防御以防并发删除。
        if not deleted:
            return
        await self._delete_checkpoint(conversation_id)

    async def _delete_checkpoint(self, conversation_id: str) -> None:
        """删掉这条 thread 在 PostgreSQL 里的 checkpoint；失败只记日志、不向上抛。"""
        checkpointer = getattr(self.graph, "checkpointer", None)
        if not isinstance(checkpointer, BaseCheckpointSaver):
            logger.warning("checkpointer 不可用，跳过 checkpoint 清理（%s）", conversation_id)
            return
        try:
            await checkpointer.adelete_thread(conversation_id)
        except Exception as exc:
            # 会话本体已删，checkpoint 清不掉只是残留一份历史记忆，不影响业务。
            logger.warning("清理会话 checkpoint 失败（%s）：%s", conversation_id, type(exc).__name__)

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
        pending_request_key = snapshot.values.get("pending_approval")
        return ConversationMessagesOut(
            conversation_id=conversation_id, items=messages[offset:offset + limit],
            total=len(messages), offset=offset, limit=limit,
            status="waiting_approval" if pending_request_key else "completed",
            pending_request_key=pending_request_key,
            running=conversation_id in self._running,
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
            # 本轮开始前还没有任何消息 = 这是首轮，结束后值得生成标题。
            was_empty = not snapshot.values.get("messages")
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
                title = await self._maybe_generate_title(db, user_id, conversation_id, content, was_empty)
                return _turn_from_state(state, conversation_id, message.id, title)
            except Exception as exc:
                # 不自动重跑：此前的工具可能已经提交了业务写入。
                logger.warning("对话执行失败（%s）", type(exc).__name__)
                raise ConversationError(
                    "本轮对话未完成，请先查看历史消息及订单、退款状态后再决定是否重新发送",
                    status_code=502,
                ) from exc
        finally:
            self._running.discard(conversation_id)

    # async def stream_message(
    #     self, db: AsyncSession, user_id: int, conversation_id: str, content: str,
    # ) -> AsyncIterator[str]:
    #     """兼容仅消费文字片段的调用方。"""
    #     stream = self.stream_turn(db, user_id, conversation_id, content)
    #     try:
    #         async for event in stream:
    #             if isinstance(event, str):
    #                 yield event
    #     finally:
    #         await stream.aclose()
##########################################################################################################################################
    async def stream_turn(
        self, db: AsyncSession, user_id: int, conversation_id: str, content: str,
    ) -> AsyncIterator[str | MessageTurnOut]:
        """先逐段产出助手文字，图执行结束后产出本轮完整结果。

        客户端断开不再让本轮作废：图始终在一个独立的后台任务里跑，用的是自己
        的数据库会话，与本次请求的生命周期解耦。断开时只中断"转发给客户端"这一步，
        图继续跑完、结果照常写入 checkpoint，之后刷新历史就能读到。
        """
        await _require_conversation(db, user_id, conversation_id)
        if conversation_id in self._running:
            raise ConversationError("本会话正在回复，请等待本轮完成", status_code=409)
        self._running.add(conversation_id)

        config = {"configurable": {"thread_id": conversation_id}}
        snapshot = await self.graph.aget_state(config)
        if snapshot.values.get("pending_approval"):
            self._running.discard(conversation_id)
            raise ConversationError("本会话正在等待管理员审批", status_code=409)
        # 本轮开始前还没有任何消息 = 这是首轮，结束后值得生成标题。
        was_empty = not snapshot.values.get("messages")
        # 认证/归属与活动时间更新都在请求的 db 上做，做完即提交、不再碰它。
        await conversation_repo.touch_conversation(db, user_id, conversation_id)
        await db.commit()

        message = HumanMessage(id=str(uuid4()), content=content)

        # 图执行用独立的数据库会话：即使客户端断开、请求结束，这个会话也不受影响，
        # 工具仍能正常读写 MySQL。由后台任务负责打开和关闭。
        worker_db = SessionLocal()
        queue: asyncio.Queue = asyncio.Queue()

        async def _run_graph() -> None:
            """在后台跑完整个图，把结果与收尾都做完，再释放锁。

            无论客户端是否还在，它都会执行到最后：正常产出文字时放进 queue，
            跑完产出完整结果，最后关闭独立会话、释放 _running 锁。
            """
            try:
                graph_stream = self.graph.astream(
                    {"messages": [message]},
                    config,
                    context=SupportContext(user_id, conversation_id, worker_db),
                    stream_mode="messages",
                    subgraphs=True,
                    version="v2",
                )
                async for part in graph_stream:
                    if part["type"] != "messages":
                        continue
                    chunk, metadata = part["data"]
                    # 意图识别也会调用模型；只把内部 Agent 的 model 节点展示给客户。
                    if metadata.get("langgraph_node") != "model":
                        continue
                    if isinstance(chunk, AIMessageChunk) and chunk.text:
                        await queue.put(("delta", str(chunk.text)))
                snapshot = await self.graph.aget_state(config)
                title = await self._maybe_generate_title(
                    worker_db, user_id, conversation_id, content, was_empty
                )
                await queue.put(("done", _turn_from_state(
                    snapshot.values, conversation_id, message.id, title
                )))
            except Exception as exc:
                # 工具可能已经写库；失败时不自动重新执行本轮。
                logger.warning("流式对话执行失败（%s）", type(exc).__name__)
                await queue.put(("error", exc))
            finally:
                await worker_db.close()
                self._running.discard(conversation_id)

        task = asyncio.create_task(_run_graph())
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "delta":
                    yield payload
                elif kind == "done":
                    yield payload
                    break
                elif kind == "error":
                    raise ConversationError(
                        "本轮对话未完成，请先查看历史消息及订单、退款状态后再决定是否重新发送",
                        status_code=502,
                    ) from payload
        finally:
            # 正常或出错路径：等后台任务收尾（关会话、释放锁）再返回。
            # 不会真正等待，后台任务得以继续在后台跑完、照常落库。
            await task

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
