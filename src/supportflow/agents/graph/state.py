
"""总图保存对话和本轮检索信息，业务办理过程保留在消息历史中。"""

from typing import Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState

Intent = Literal[
    "order_query", "refund_request", "refund_query",
    "product_support", "policy_question", "unknown",
]
NextNode = Literal["support_agent", "retrieve_knowledge", "search_web", "wait_for_approval", "end"]
RetrievalStatus = Literal["not_requested", "unavailable", "empty", "ready"]
WebSearchStatus = Literal["not_requested", "unavailable", "empty", "ready"]


class KnowledgeState(TypedDict):
    question: str | None
    product_model: str | None


class RetrievedDocument(TypedDict):
    document_id: str
    chunk_id: str
    title: str
    source: str
    content: str
    section: NotRequired[str]
    category: NotRequired[str]
    score: NotRequired[float]


class WebSource(TypedDict):
    title: str
    url: str
    content: str


class SupportState(MessagesState):
    # messages 由 add_messages 合并；其他字段整体替换，不自动深度合并。
    current_intent: Intent
    next_node: NextNode | None
    knowledge: KnowledgeState
    retrieved_documents: list[RetrievedDocument]
    retrieval_status: RetrievalStatus
    web_search_status: WebSearchStatus
    web_sources: list[WebSource]
    pending_approval: str | None


class SupportStateUpdate(TypedDict, total=False):
    """节点只返回本次要更新的字段，不修改输入 State。"""

    messages: list[AnyMessage]
    current_intent: Intent
    next_node: NextNode | None
    knowledge: KnowledgeState
    retrieved_documents: list[RetrievedDocument]
    retrieval_status: RetrievalStatus
    web_search_status: WebSearchStatus
    web_sources: list[WebSource]
    pending_approval: str | None


def initial_state() -> SupportState:
    """新会话的默认值；后续轮次只传新增 messages，让 checkpoint 恢复历史。"""
    return {
        "messages": [],
        "current_intent": "unknown",
        "next_node": None,
        "knowledge": {"question": None, "product_model": None},
        "retrieved_documents": [],
        "retrieval_status": "not_requested",
        "web_search_status": "not_requested",
        "web_sources": [],
        "pending_approval": None,
    }
