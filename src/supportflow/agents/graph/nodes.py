"""总图节点：识别需求 → 可选知识检索 → 统一售后 Agent。

State 保存历史；Runtime.context 提供本次执行的身份与数据库连接。
只有总图保存多轮记忆，内部 Agent 使用传入的历史并返回新增消息。
"""
import json
import logging

from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from supportflow.agents.agent.support_agent import SUPPORT_STREAM_TAG, build_support_agent
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState, SupportStateUpdate
from supportflow.agents.prompt.routing import ROUTING_SYSTEM_PROMPT
from supportflow.agents.structured_output.node_output import UnderstandAndRouteOutput
from supportflow.retrieval.hybrid import retrieve_hybrid as retrieve
from supportflow.retrieval.types import RetrievalUnavailable

logger = logging.getLogger(__name__)


def _get_router_model():
    # 导入、编译和画图不初始化模型客户端。
    from supportflow.agents.llm import chat_model

    # 结构化路由会强制选择输出工具；DeepSeek 思考模式不支持指定 tool_choice。
    # 仅为路由复制配置，保留售后 Agent 原本的模型设置。
    router_model = chat_model.model_copy(update={
        "extra_body": {**(chat_model.extra_body or {}), "thinking": {"type": "disabled"}},
    })
    return router_model.with_structured_output(UnderstandAndRouteOutput)


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
    """双路召回后按 RRF 融合本轮证据，区分无匹配和服务失败。"""
    update: SupportStateUpdate = {
        "retrieved_documents": [],
        "retrieval_status": "empty",
        "next_node": "support_agent",
    }
    knowledge = state.get("knowledge", {})
    question = (knowledge.get("question") or "").strip()
    if not question:
        return update
    product_model = (knowledge.get("product_model") or "").strip()
    # 当前库未存统一型号字段，补入查询上下文，不声称这是严格的型号过滤。
    if product_model and product_model.casefold() not in question.casefold():
        question = f"商品型号：{product_model}\n问题：{question}"
    try:
        documents = await retrieve(question)
    except RetrievalUnavailable as exc:
        logger.warning("%s", exc)
        update["retrieval_status"] = "unavailable"
        return update
    update["retrieved_documents"] = documents
    update["retrieval_status"] = "ready" if documents else "empty"
    return update


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
    # 标记内部 Agent 的模型调用，HTTP messages 流据此排除路由模型输出。
    result = await agent.ainvoke({"messages": history}, config={"tags": [SUPPORT_STREAM_TAG]})
    # Agent 返回完整历史，只回传本次增量。保留所有 AI 工具调用和 ToolMessage，
    # 不可只取最后一条回复，否则下一轮会丢失工具事实和调用配对。
    return {"messages": result["messages"][len(history):], "next_node": "end"}
