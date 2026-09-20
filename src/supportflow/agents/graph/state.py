"""售后总图的对话状态，由 checkpoint 按 thread_id 保存。

messages 继承 MessagesState 的消息合并规则；其余字段按顶层键替换，
不会自动深度合并。例如更新退款原因时，应返回完整的退款子状态：
    {"refund": {**state["refund"], "reason": reason}}

这里的类型用于描述节点协议，不代替业务层的归属、资格和参数校验。
"""

from typing import Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import MessagesState


Intent = Literal[
    "order_query",
    "refund_request",
    "refund_query",
    "product_support",
    "policy_question",
    "unknown",
]

NextNode = Literal[
    "order_agent", "refund_agent", "prepare_knowledge", "retrieve_knowledge",
    "clarify", "end",
]

OrderPurpose = Literal["order_query", "refund", "knowledge"]
RefundPhase = Literal[
    "idle", "need_order", "check_eligibility", "need_reason",
    "ready_submit", "submitted",
]
KnowledgeTopic = Literal["product_support", "policy"]


class OrderState(TypedDict):
    """订单定位结果；候选不代表用户已确认，不能直接用来提交退款。"""

    candidate_order_nos: list[str]
    selected_order_no: str | None
    # 订单可能有多个商品，确认订单不等于确认了某个商品型号。
    product_code: str | None
    product_model: str | None
    purpose: OrderPurpose | None


class RefundState(TypedDict):
    """独立保存退款进度，中途咨询政策时不清空。"""

    phase: RefundPhase
    order_no: str | None
    reason: str | None
    # 只接受业务工具返回的申请编号，不由模型编造。
    request_key: str | None


class KnowledgeState(TypedDict):
    """检索节点的输入；商品型号不明时可先追问或定位订单。"""

    topic: KnowledgeTopic | None
    question: str | None
    product_model: str | None


class RetrievedDocument(TypedDict):
    """检索节点交给回答节点的证据片段，使用可持久化的普通字段。"""

    document_id: str
    chunk_id: str
    title: str
    source: str  # 文档地址或知识库内可定位的来源标识
    content: str


class SupportState(MessagesState):
    current_intent: Intent
    next_node: NextNode | None
    order: OrderState
    refund: RefundState
    knowledge: KnowledgeState
    # 本轮检索证据，默认整体替换而非累加。准备新问题/型号时先清空，
    # 检索无结果也必须写入 []，避免回答节点误用上一轮证据。
    retrieved_documents: list[RetrievedDocument]


class SupportStateUpdate(TypedDict, total=False):
    """节点只返回本次更新的顶层字段；子状态仍需整体返回。"""

    messages: list[AnyMessage]
    current_intent: Intent
    next_node: NextNode | None
    order: OrderState
    refund: RefundState
    knowledge: KnowledgeState
    retrieved_documents: list[RetrievedDocument]


def initial_state() -> SupportState:
    """仅在创建新会话时使用，每次返回独立的字典和列表。

    后续轮次只传新增 messages，让 checkpoint 恢复已保存的业务进度。
    更换退款订单或取消任务时，由后续节点显式清理相应子状态；
    本模块只定义数据结构，不执行流程判断或数据库操作。
    """
    return {
        "messages": [],
        "current_intent": "unknown",
        "next_node": None,
        "order": {
            "candidate_order_nos": [],
            "selected_order_no": None,
            "product_code": None,
            "product_model": None,
            "purpose": None,
        },
        "refund": {
            "phase": "idle",
            "order_no": None,
            "reason": None,
            "request_key": None,
        },
        "knowledge": {
            "topic": None,
            "question": None,
            "product_model": None,
        },
        "retrieved_documents": [],
    }
