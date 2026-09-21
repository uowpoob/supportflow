"""总图节点：识别需求 → 可选知识检索 → 统一售后 Agent。

State 保存历史；Runtime.context 提供本次执行的身份与数据库连接。
只有总图保存多轮记忆，内部 Agent 使用传入的历史并返回新增消息。
"""
import json

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from supportflow.agents.agent.support_agent import build_support_agent
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState, SupportStateUpdate
from supportflow.agents.prompt.routing import ROUTING_SYSTEM_PROMPT
from supportflow.agents.structured_output.node_output import UnderstandAndRouteOutput


def _get_router_model():
    # 导入、编译和画图不初始化模型客户端。
    from supportflow.agents.llm import chat_model

    return chat_model.with_structured_output(UnderstandAndRouteOutput)


async def understand_and_route(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """识别本轮是否需要检索；订单定位、原因追问等均由同一个 Agent 处理。"""
    if not state.get("messages"):
        raise ValueError("意图识别需要非空的 messages")

    result = await _get_router_model().ainvoke([
        SystemMessage(content=ROUTING_SYSTEM_PROMPT),
        *state["messages"],
    ])
    needs_knowledge = result.intent in ("product_support", "policy_question")
    return {
        "current_intent": result.intent,
        "next_node": "retrieve_knowledge" if needs_knowledge else "support_agent",
        "knowledge": {
            "question": result.knowledge_question if needs_knowledge else None,
            "product_model": result.product_model if needs_knowledge else None,
        },
        # 每轮重新检索，包含转回退款或切换商品的情况，禁止复用旧证据。
        "retrieved_documents": [],
        "retrieval_status": "not_requested",
    }


async def retrieve_knowledge(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """知识库接入位置，目前明确返回不可用，不伪造检索结果。

    后续用 state['knowledge'] 调检索服务，返回带来源的文档。
    接入后，有结果设置 ready，无匹配设置 empty，两者都整体替换文档列表。
    此节点不回答用户，也不创建新 Agent。
    """
    return {
        "retrieved_documents": [],
        "retrieval_status": "unavailable",
        "next_node": "support_agent",
    }


async def support_agent(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """统一查询、追问、提交或根据本轮文档回答，然后结束本轮。"""
    context = runtime.context
    knowledge_context = None
    if state["current_intent"] in ("product_support", "policy_question"):
        # 证据仅供本轮模型读取，不追加到长期消息历史。
        knowledge_context = json.dumps({
            "query": state["knowledge"],
            "status": state["retrieval_status"],
            "documents": state["retrieved_documents"],
        }, ensure_ascii=False)

    agent = build_support_agent(
        context.db,
        context.user_id,
        context.conversation_id,
        checkpointer=False,
        knowledge_context=knowledge_context,
    )
    history = state["messages"]
    result = await agent.ainvoke({"messages": history})
    # Agent 返回完整历史，只回传本次增量。保留所有 AI 工具调用和 ToolMessage，
    # 不可只取最后一条回复，否则下一轮会丢失工具事实和调用配对。
    return {"messages": result["messages"][len(history):], "next_node": "end"}
