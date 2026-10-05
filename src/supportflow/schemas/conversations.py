"""客户会话接口的输入和输出，不向客户端暴露内部工具消息。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from supportflow.agents.graph.state import RetrievalStatus
from supportflow.models.entities import Conversation
from supportflow.schemas.common import UtcInstant


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(default="新会话", min_length=1, max_length=200)


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: UtcInstant
    updated_at: UtcInstant

    @classmethod
    def from_row(cls, conversation: Conversation) -> "ConversationOut":
        return cls(
            id=UUID(conversation.id),
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationPage(BaseModel):
    items: list[ConversationOut]
    total: int = Field(description="当前用户的会话总数，与当前页无关")
    offset: int
    limit: int


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=8000)


class ChatMessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str


class ConversationMessagesOut(BaseModel):
    conversation_id: UUID
    items: list[ChatMessageOut]
    total: int
    offset: int
    limit: int
    status: Literal["completed", "waiting_approval"]
    pending_request_key: str | None = None


class RetrievedSourceOut(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    source: str
    section: str | None = None
    score: float | None = None


class MessageTurnOut(BaseModel):
    conversation_id: UUID
    messages: list[ChatMessageOut]
    status: Literal["completed", "waiting_approval"]
    pending_request_key: str | None = None
    retrieval_status: RetrievalStatus
    retrieved_sources: list[RetrievedSourceOut]
    # 首轮后自动生成的标题；非首轮或生成失败时为 None，前端不更新。
    title: str | None = None
