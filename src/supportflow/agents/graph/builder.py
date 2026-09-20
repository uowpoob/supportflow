"""售后总图连线；可编译和画图，业务节点仍是显式占位实现。"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from supportflow.agents.graph import nodes
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState


def _destination(state: SupportState, allowed: tuple[str, ...]) -> str:
    destination = state.get("next_node")
    if destination not in allowed:
        raise ValueError(
            f"节点必须设置有效的 next_node，允许 {allowed}，实际为 {destination!r}"
        )
    return destination


def after_understanding(state: SupportState) -> str:
    return _destination(state, (
        "order_agent", "refund_agent", "prepare_knowledge", "clarify", "end",
    ))


def after_order(state: SupportState) -> str:
    # 由订单节点明确决定是否交接，避免凭旧的 selected_order_no 自动发起退款。
    return _destination(state, ("refund_agent", "prepare_knowledge", "clarify", "end"))


def after_knowledge_preparation(state: SupportState) -> str:
    return _destination(state, ("retrieve_knowledge", "clarify"))


def build_support_graph(*, checkpointer: BaseCheckpointSaver | None = None):
    """只构造图，不执行节点、不调用模型、不连接数据库。

    END 表示本轮结束。未来调用时使用同一 thread_id 恢复会话，并每次传入
    SupportContext；HTTP 认证、会话归属校验与接口接入不在这里实现。
    """
    graph = StateGraph(SupportState, context_schema=SupportContext)

    graph.add_node("understand_and_route", nodes.understand_and_route)
    graph.add_node("order_agent", nodes.order_agent)
    graph.add_node("refund_agent", nodes.refund_agent)
    graph.add_node("prepare_knowledge", nodes.prepare_knowledge)
    graph.add_node("retrieve_knowledge", nodes.retrieve_knowledge)
    graph.add_node("answer_knowledge", nodes.answer_knowledge)
    graph.add_node("clarify", nodes.clarify)

    graph.add_edge(START, "understand_and_route")
    graph.add_conditional_edges("understand_and_route", after_understanding, {
        "order_agent": "order_agent",
        "refund_agent": "refund_agent",
        "prepare_knowledge": "prepare_knowledge",
        "clarify": "clarify",
        "end": END,
    })
    graph.add_conditional_edges("order_agent", after_order, {
        "refund_agent": "refund_agent",
        "prepare_knowledge": "prepare_knowledge",
        "clarify": "clarify",
        "end": END,
    })
    graph.add_conditional_edges("prepare_knowledge", after_knowledge_preparation, {
        "retrieve_knowledge": "retrieve_knowledge",
        "clarify": "clarify",
    })
    graph.add_edge("retrieve_knowledge", "answer_knowledge")
    graph.add_edge("answer_knowledge", END)
    graph.add_edge("refund_agent", END)
    graph.add_edge("clarify", END)

    return graph.compile(checkpointer=checkpointer)
