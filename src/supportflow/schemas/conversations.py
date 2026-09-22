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


class RetrievedSourceOut(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    source: str
    section: str | None = None
    score: float | None = None


class MessageTurnOut(BaseModel):
    """SSE done 事件：本轮最终消息与来源，用于校正前端的临时流式显示。"""

    conversation_id: UUID
    messages: list[ChatMessageOut]
    retrieval_status: RetrievalStatus
    retrieved_sources: list[RetrievedSourceOut]


class MessageStartOut(BaseModel):
    conversation_id: UUID
    message: ChatMessageOut


class MessageDeltaOut(BaseModel):
    message_id: str
    delta: str


class MessageStreamErrorOut(BaseModel):
    code: Literal["conversation_failed"] = "conversation_failed"
    message: str


MessageStreamEvent = tuple[
    str, MessageStartOut | MessageDeltaOut | MessageTurnOut | MessageStreamErrorOut,
]
