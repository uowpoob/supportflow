"""客户会话与 SSE 消息接口；conversation_id 与 thread_id 使用同一个 UUID。"""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.api.auth.deps import require_customer
from supportflow.db.session import get_db
from supportflow.models.entities import User
from supportflow.schemas.conversations import (
    ConversationCreate, ConversationMessagesOut, ConversationOut, ConversationPage,
    MessageCreate, MessageStreamEvent,
)
from supportflow.schemas.result import Success
from supportflow.services import conversations as conversation_service
from supportflow.services.conversations import ConversationChat, ConversationError

router = APIRouter(tags=["customer"])


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


async def _sse_events(events: AsyncIterator[MessageStreamEvent]) -> AsyncIterator[str]:
    async for event, data in events:
        # JSON 会转义正文换行，防止文字被误解析为新的 SSE 字段或事件。
        yield f"event: {event}\ndata: {data.model_dump_json()}\n\n"


async def _message_stream(
    conversation_id: UUID,
    payload: MessageCreate,
    request: Request,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db, scope="request"),
) -> AsyncIterator[AsyncIterator[str]]:
    """在响应头发送前完成归属/占用校验，流关闭后才退出上下文。"""
    try:
        async with _chat(request).stream_message(db, user.id, str(conversation_id), payload.content) as events:
            yield _sse_events(events)
    except ConversationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={200: {"description": "SSE 消息流：start、message、done 或 error", "content": {"text/event-stream": {}}}},
)
async def send_message(
    stream: AsyncIterator[str] = Depends(_message_stream, scope="request"),
) -> StreamingResponse:
    """只流式返回售后 Agent 的文字；done 事件包含本轮最终消息和检索来源。"""
    return StreamingResponse(
        stream, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
