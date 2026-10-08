"""客户会话与消息接口；conversation_id 与 thread_id 使用同一个 UUID。"""

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.api.auth.deps import require_customer
from supportflow.db.session import get_db
from supportflow.models.entities import User
from supportflow.schemas.conversations import (
    ConversationCreate, ConversationMessagesOut, ConversationOut, ConversationPage,
    MessageCreate, MessageTurnOut,
)
from supportflow.schemas.result import Success
from supportflow.services import conversations as conversation_service
from supportflow.services.conversations import ConversationChat, ConversationError

router = APIRouter(tags=["customer"])
logger = logging.getLogger(__name__)


def _chat(request: Request) -> ConversationChat:
    chat = getattr(request.app.state, "conversation_chat", None)
    if chat is None:
        raise HTTPException(status_code=503, detail="对话服务尚未就绪")
    return chat


@router.post("/conversations", response_model=Success[ConversationOut], status_code=201)
async def create_conversation(
    payload: ConversationCreate = Body(default_factory=ConversationCreate),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[ConversationOut]:
    """创建自己的会话；ID 由服务端生成 UUID，不接受 user_id 或 thread_id。"""
    row = await conversation_service.create_conversation(db, user.id, payload.title)
    return Success[ConversationOut](data=ConversationOut.from_row(row))


@router.get("/conversations", response_model=Success[ConversationPage])
async def list_conversations(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[ConversationPage]:
    """我的会话，按最近活动时间倒序分页。"""
    rows, total = await conversation_service.list_conversations_for_user(db, user.id, offset, limit)
    return Success[ConversationPage](data=ConversationPage(
        items=[ConversationOut.from_row(row) for row in rows], total=total, offset=offset, limit=limit,
    ))


@router.delete("/conversations/{conversation_id}", response_model=Success[dict])
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[dict]:
    """删除自己的会话，连带清掉挂在它上面的退款申请和对话历史。

    别人的会话与不存在的会话统一 404；正在回复的会话 409（先等本轮跑完）。
    """
    try:
        await _chat(request).delete_conversation(db, user.id, str(conversation_id))
    except ConversationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Success[dict](data={})


@router.get("/conversations/{conversation_id}/messages", response_model=Success[ConversationMessagesOut])
async def list_messages(
    conversation_id: UUID,
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[ConversationMessagesOut]:
    """归属校验后读取 checkpoint，仅返回按时间顺序排列的用户消息和助手答复。"""
    try:
        page = await _chat(request).list_messages(db, user.id, str(conversation_id), offset, limit)
    except ConversationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Success[ConversationMessagesOut](data=page)


@router.post("/conversations/{conversation_id}/messages", response_model=Success[MessageTurnOut])
async def send_message(
    conversation_id: UUID,
    payload: MessageCreate,
    request: Request,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> Success[MessageTurnOut]:
    """发送一条新消息，等待本轮完成后返回增量消息及本轮检索来源。"""
    try:
        turn = await _chat(request).send_message(db, user.id, str(conversation_id), payload.content)
    except ConversationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Success[MessageTurnOut](data=turn)


@router.post("/conversations/{conversation_id}/messages/stream", response_class=EventSourceResponse)
async def stream_message(
    conversation_id: UUID,
    payload: MessageCreate,
    chat: ConversationChat = Depends(_chat),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
) -> AsyncIterator[ServerSentEvent]:
    """逐段发送助手文字，并在图结束后发送本轮完整结果。"""
    stream = chat.stream_turn(db, user.id, str(conversation_id), payload.content)
    try:
        async for item in stream:
            if isinstance(item, MessageTurnOut):
                yield ServerSentEvent(event="done", data=item)
            else:
                yield ServerSentEvent(event="delta", data={"text": item})
    except ConversationError as exc:
        # SSE 响应头可能已经发出，不能再用 HTTP 状态码表示本轮失败。
        yield ServerSentEvent(event="error", data={"status": exc.status_code, "message": exc.message})
    except Exception:
        logger.exception("流式响应失败")
        yield ServerSentEvent(event="error", data={
            "status": 502,
            "message": "本轮对话未完成，请先查看历史消息及订单、退款状态后再决定是否重新发送",
        })
    finally:
        await stream.aclose()
