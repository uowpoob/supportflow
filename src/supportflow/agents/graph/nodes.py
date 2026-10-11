"""总图节点：识别需求 → 可选知识检索 → 统一售后 Agent。

State 保存历史；Runtime.context 提供本次执行的身份与数据库连接。
只有总图保存多轮记忆，内部 Agent 使用传入的历史并返回新增消息。
"""
import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from supportflow.agents.agent.support_agent import build_support_agent
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import SupportState, SupportStateUpdate
from supportflow.agents.prompt.routing import ROUTING_SYSTEM_PROMPT
from supportflow.agents.structured_output.node_output import UnderstandAndRouteOutput
from supportflow.agents.tools.web_search import WebSearchUnavailable, search_web as web_search
from supportflow.agents.tools.knowledge_check import has_sufficient_knowledge
from supportflow.core.config import settings
from supportflow.retrieval.retrieving.hybrid import retrieve_hybrid as retrieve
from supportflow.retrieval.types import RetrievalUnavailable
from supportflow.models.enums import RefundStatus
from supportflow.services.refunds import get_refund_request_for_user

logger = logging.getLogger(__name__)


def _routing_history(messages):
    """挑出给意图识别看的消息：只要用户说了什么、助手答了什么。
    """
    return [
        message
        for message in messages
        if isinstance(message, HumanMessage)
        or (isinstance(message, AIMessage) and not message.tool_calls)
    ]


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
        *_routing_history(state["messages"]),
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
        "web_search_status": "not_requested",
        "web_sources": [],
    }


def _knowledge_query(state: SupportState) -> str:
    """优先用路由整理的问题；缺失时用最后一条用户消息，避免静默跳过兜底。"""
    knowledge = state.get("knowledge", {})
    question = (knowledge.get("question") or "").strip()
    if not question:
        question = next((
            message.text.strip() for message in reversed(state.get("messages", []))
            if isinstance(message, HumanMessage) and message.text.strip()
        ), "")
    product_model = (knowledge.get("product_model") or "").strip()
    # 当前库未存统一型号字段，补入查询上下文，不声称这是严格的型号过滤。
    if question and product_model and product_model.casefold() not in question.casefold():
        question = f"商品型号：{product_model}\n问题：{question}"
    return question


async def retrieve_knowledge(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """双路召回后按 RRF 融合本轮证据，区分无匹配和服务失败。"""
    update: SupportStateUpdate = {
        "retrieved_documents": [],
        "retrieval_status": "empty",
        "web_search_status": "not_requested",
        "web_sources": [],
        "next_node": "search_web",
    }
    question = _knowledge_query(state)
    if not question:
        return update
    try:
        # 重排开关默认开（见 config.RETRIEVAL_RERANK）；重排自己失败时会退回融合顺序，
        # 不会因为这一个环节挂掉就让本轮拿不到证据。
        documents = await retrieve(question, rerank=settings.RETRIEVAL_RERANK)
    except RetrievalUnavailable as exc:
        logger.warning("%s", exc)
        update["retrieval_status"] = "unavailable"
        return update
    if documents and not await has_sufficient_knowledge(question, documents):
        # 不把未通过审核的候选继续交给回答模型，避免混入无关依据。
        return update
    update["retrieved_documents"] = documents
    update["retrieval_status"] = "ready" if documents else "empty"
    if documents:
        update["next_node"] = "support_agent"
    return update


async def search_web(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """本地检索失败后搜索公开网页；保留本地状态，供回答和页面披露来源。"""
    update: SupportStateUpdate = {
        "web_sources": [], "web_search_status": "empty", "next_node": "support_agent",
    }
    question = _knowledge_query(state)
    if not question:
        return update
    try:
        sources = await web_search(question)
    except WebSearchUnavailable as exc:
        logger.warning("%s", exc)
        update["web_search_status"] = "unavailable"
        return update
    update["web_sources"] = sources
    update["web_search_status"] = "ready" if sources else "empty"
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
            "web_search_status": state.get("web_search_status", "not_requested"),
            "web_sources": state.get("web_sources", []),
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
    added = result["messages"][len(history):]
    submitted = [
        message.artifact["request_key"]
        for message in added
        if isinstance(message, ToolMessage)
        and message.name == "post_refund"
        and isinstance(message.artifact, dict)
        and message.artifact.get("status") == RefundStatus.PENDING.value
        and message.artifact.get("conversation_id") == context.conversation_id
    ]
    if len(set(submitted)) > 1:
        raise ValueError("同一轮提交了多个待审批申请")
    return {
        "messages": added,
        "pending_approval": submitted[0] if submitted else None,
        "next_node": "wait_for_approval" if submitted else "end",
    }


async def wait_for_approval(
    state: SupportState, runtime: Runtime[SupportContext],
) -> SupportStateUpdate:
    """只在外层图暂停；恢复后以 MySQL 的审批结果为准。"""
    request_key = state["pending_approval"]
    if not request_key:
        raise ValueError("缺少待审批申请编号")
    signal = interrupt({"type": "refund_approval", "request_key": request_key})
    if not isinstance(signal, dict) or signal.get("request_key") != request_key:
        raise ValueError("审批恢复信号与申请不匹配")

    context = runtime.context
    view = await get_refund_request_for_user(context.db, context.user_id, request_key)
    if view is None or view.request.conversation_id != context.conversation_id:
        raise ValueError("审批申请与当前会话不匹配")
    if view.request.status == RefundStatus.PENDING:
        raise ValueError("申请仍在待审批状态")
    if view.request.status == RefundStatus.REJECTED:
        text = f"申请 {request_key} 未获批准。"
        if view.approval and view.approval.comment:
            text += f"审批备注：{view.approval.comment}"
    elif view.request.status == RefundStatus.REFUNDED:
        text = f"申请 {request_key} 已获批准，模拟退款已完成。"
    else:
        text = f"申请 {request_key} 已获批准，当前状态：{view.request.status.value}。"
    return {
        "messages": [AIMessage(content=text)],
        "pending_approval": None,
        "next_node": "end",
    }
