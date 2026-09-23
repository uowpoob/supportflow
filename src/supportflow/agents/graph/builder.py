"""单 Agent 总图；订单和退款不再分支交接，知识检索仍是普通节点。"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from supportflow.agents.graph import nodes
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState


def after_understanding(state: SupportState) -> str:
    destination = state.get("next_node")
    if destination not in ("support_agent", "retrieve_knowledge"):
        raise ValueError(f"意图节点返回了无效的 next_node：{destination!r}")
    return destination


def after_agent(state: SupportState) -> str:
    return "wait_for_approval" if state.get("pending_approval") else "end"


def build_support_graph(*, checkpointer: BaseCheckpointSaver | None = None):
    """只构造图；HTTP 服务启动时构建并复用，执行时传入本次 SupportContext。

    总图负责 checkpoint；END 只结束本轮，下一轮传新增消息恢复会话。
    """
    graph = StateGraph(SupportState, context_schema=SupportContext)
    graph.add_node("understand_and_route", nodes.understand_and_route)
    graph.add_node("retrieve_knowledge", nodes.retrieve_knowledge)
    graph.add_node("support_agent", nodes.support_agent)
    graph.add_node("wait_for_approval", nodes.wait_for_approval)

    graph.add_edge(START, "understand_and_route")
    graph.add_conditional_edges("understand_and_route", after_understanding, {
        "support_agent": "support_agent",
        "retrieve_knowledge": "retrieve_knowledge",
    })
    graph.add_edge("retrieve_knowledge", "support_agent")
    graph.add_conditional_edges("support_agent", after_agent, {
        "wait_for_approval": "wait_for_approval", "end": END,
    })
    graph.add_edge("wait_for_approval", END)
    return graph.compile(checkpointer=checkpointer)
