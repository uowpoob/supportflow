"""单 Agent 总图的离线测试，不连接业务库、知识库或真实模型。"""

import asyncio
import json
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from pydantic import Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.graph import nodes
from supportflow.agents.graph.builder import build_support_graph
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import initial_state
from supportflow.agents.structured_output.node_output import UnderstandAndRouteOutput
from supportflow.agents.tools import order_tools, refund_tools
from supportflow.services import conversations as conversation_service


def mock_router(monkeypatch, intent, **kwargs):
    model = Mock()
    model.ainvoke = AsyncMock(return_value=UnderstandAndRouteOutput(intent=intent, **kwargs))
    monkeypatch.setattr(nodes, "_get_router_model", lambda: model)
    return model


def context():
    return SupportContext(4, "route-test", Mock(spec=AsyncSession))


@pytest.mark.asyncio
async def test_router_request_disables_thinking_for_forced_tool_choice(monkeypatch):
    import httpx
    from langchain_deepseek import ChatDeepSeek

    def respond(request):
        payload = json.loads(request.content)
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["tool_choice"]["function"]["name"] == "UnderstandAndRouteOutput"
        return httpx.Response(200, json={
            "id": "offline-router", "model": "deepseek-v4-flash", "object": "chat.completion",
            "created": 0, "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "route-1", "type": "function", "function": {
                        "name": "UnderstandAndRouteOutput",
                        "arguments": json.dumps({"intent": "policy_question", "knowledge_question": "运费谁承担？"}),
                    },
                }],
            }}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        chat_model = ChatDeepSeek(
            model="deepseek-v4-flash", api_key="offline-test",
            http_async_client=http_client, extra_body={"thinking": {"type": "enabled"}},
        )
        monkeypatch.setitem(sys.modules, "supportflow.agents.llm", SimpleNamespace(chat_model=chat_model))
        result = await nodes._get_router_model().ainvoke([HumanMessage(content="运费谁承担？")])
        assert result.intent == "policy_question"
        assert chat_model.extra_body == {"thinking": {"type": "enabled"}}


@pytest.mark.parametrize("payload", [
    {"intent": "invented"},
    {"intent": "order_query", "next_node": "order_agent"},
    {"intent": "order_query", "user_id": 9},
])
def test_schema_rejects_invalid_or_extra_fields(payload):
    with pytest.raises(ValidationError):
        UnderstandAndRouteOutput.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("intent,expected", [
    ("order_query", "support_agent"),
    ("refund_query", "support_agent"),
    ("refund_request", "support_agent"),
    ("unknown", "support_agent"),
    ("policy_question", "retrieve_knowledge"),
    ("product_support", "retrieve_knowledge"),
])
async def test_routes_and_clears_previous_evidence(monkeypatch, intent, expected):
    model = mock_router(monkeypatch, intent)
    state = initial_state()
    state["messages"] = [HumanMessage(content="本轮问题")]
    state["knowledge"] = {"question": "旧问题", "product_model": "旧型号"}
    state["retrieved_documents"] = [{"content": "上轮证据"}]
    state["retrieval_status"] = "ready"
    before = deepcopy(state)
    result = await nodes.understand_and_route(state, Runtime(context=context()))
    assert result["next_node"] == expected
    assert result["current_intent"] == intent
    assert result["knowledge"] == {"question": None, "product_model": None}
    assert result["retrieved_documents"] == []
    assert result["retrieval_status"] == "not_requested"
    assert model.ainvoke.await_args.args[0][1:] == state["messages"]
    assert "messages" not in result
    assert state == before


@pytest.mark.asyncio
async def test_new_conversation_prepares_knowledge(monkeypatch):
    mock_router(monkeypatch, "product_support", knowledge_question="X1 如何开机？", product_model="X1")
    result = await nodes.understand_and_route(
        {"messages": [HumanMessage(content="它怎么开机？")]}, Runtime(context=context()),
    )
    assert result["knowledge"] == {"question": "X1 如何开机？", "product_model": "X1"}
    assert result["next_node"] == "retrieve_knowledge"


@pytest.mark.asyncio
async def test_empty_history_does_not_call_model(monkeypatch):
    model = mock_router(monkeypatch, "unknown")
    with pytest.raises(ValueError, match="messages"):
        await nodes.understand_and_route(initial_state(), Runtime(context=context()))
    model.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_question_clears_documents_without_retrieval(monkeypatch):
    retrieval = AsyncMock()
    monkeypatch.setattr(nodes, "retrieve", retrieval)
    state = initial_state()
    state["retrieved_documents"] = [{"content": "旧证据"}]
    result = await nodes.retrieve_knowledge(state, Runtime(context=context()))
    assert result["retrieval_status"] == "empty"
    assert result["retrieved_documents"] == []
    retrieval.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ready", "empty", "unavailable"])
async def test_retrieval_node_updates_only_current_evidence(monkeypatch, outcome):
    document = {
        "document_id": "x1", "chunk_id": "x1#1", "title": "X1 使用指南",
        "source": "data/x1.md", "content": "长按开机键", "score": 0.8,
        "category": "data", "section": "开机",
    }
    retrieval = AsyncMock(return_value=[document] if outcome == "ready" else [])
    if outcome == "unavailable":
        retrieval.side_effect = nodes.RetrievalUnavailable("测试服务不可用")
    monkeypatch.setattr(nodes, "retrieve", retrieval)
    state = initial_state()
    state["knowledge"] = {"question": "如何开机？", "product_model": "X1"}
    state["retrieved_documents"] = [{"content": "旧证据"}]
    before = deepcopy(state)
    result = await nodes.retrieve_knowledge(state, Runtime(context=context()))
    assert result["retrieval_status"] == outcome
    assert result["retrieved_documents"] == ([document] if outcome == "ready" else [])
    assert result["next_node"] == "support_agent"
    assert state == before
    assert "messages" not in result
    retrieval.assert_awaited_once_with("商品型号：X1\n问题：如何开机？")


class ScriptedModel(BaseChatModel):
    """走真实 create_agent 和 ToolNode，只替换模型响应及数据库服务。"""

    responses: list[AIMessage]
    seen: list[list] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "offline-graph-test"

    def bind_tools(self, tools, **kwargs):
        assert {tool.name for tool in tools} == {
            "get_order_detail", "list_my_orders", "get_order_item",
            "list_my_refunds", "get_refund_detail", "get_refund_eligibility", "post_refund",
        }
        for tool in tools:
            properties = tool.args_schema.model_json_schema().get("properties", {})
            assert not {"user_id", "conversation_id", "db"} & properties.keys()
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


def use_model(monkeypatch, responses):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    model = ScriptedModel(responses=responses)
    monkeypatch.setitem(sys.modules, "supportflow.agents.llm", SimpleNamespace(chat_model=model))
    return model


@pytest.mark.asyncio
async def test_real_agent_graph_preserves_tool_pairs_and_memory_across_topics(monkeypatch):
    monkeypatch.setattr(nodes, "retrieve", AsyncMock(side_effect=nodes.RetrievalUnavailable("离线模拟")))
    router = mock_router(monkeypatch, "order_query")
    model = use_model(monkeypatch, [
        AIMessage(content="", tool_calls=[{"name": "list_my_orders", "args": {}, "id": "orders-1"}]),
        AIMessage(content="没有订单"),
        AIMessage(content="当前没有相应的使用资料"),
        AIMessage(content="", tool_calls=[{"name": "list_my_refunds", "args": {}, "id": "refunds-1"}]),
        AIMessage(content="没有退款申请"),
    ])
    orders = AsyncMock(return_value=([], 0))
    refunds = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(order_tools.order_service, "list_orders_for_user", orders)
    monkeypatch.setattr(refund_tools.refund_service, "list_refund_requests_for_user", refunds)
    graph = build_support_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "route-test"}}
    ctx = context()

    first = await graph.ainvoke({"messages": [("user", "我的订单")]}, config, context=ctx)
    assert [m.type for m in first["messages"]] == ["human", "ai", "tool", "ai"]
    assert first["messages"][2].tool_call_id == "orders-1"

    router.ainvoke.return_value = UnderstandAndRouteOutput(
        intent="product_support", knowledge_question="X1 怎么开机？", product_model="X1",
    )
    second = await graph.ainvoke({"messages": [("user", "X1 怎么开机？")]}, config, context=ctx)
    assert len(second["messages"]) == 6
    assert second["retrieval_status"] == "unavailable"
    assert '"status": "unavailable"' in model.seen[2][0].content

    router.ainvoke.return_value = UnderstandAndRouteOutput(intent="refund_query")
    third = await graph.ainvoke({"messages": [("user", "我的退款记录")]}, config, context=ctx)
    assert len(third["messages"]) == 10
    assert [m.type for m in third["messages"]].count("tool") == 2
    assert third["next_node"] == "end"
    assert third["retrieval_status"] == "not_requested"
    assert third["knowledge"] == {"question": None, "product_model": None}
    assert "本轮检索数据" not in model.seen[3][0].content
    assert not any(m.type == "system" for m in third["messages"])
    assert not {"db", "user_id", "conversation_id"} & third.keys()
    orders.assert_awaited_once_with(ctx.db, 4, offset=0, limit=50)
    refunds.assert_awaited_once_with(ctx.db, 4, offset=0, limit=50, status=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision_status,expected", [
    (refund_tools.RefundStatus.REFUNDED, "模拟退款已完成"),
    (refund_tools.RefundStatus.REJECTED, "未获批准"),
])
async def test_refund_tool_uses_runtime_identity_and_conversation(monkeypatch, decision_status, expected):
    mock_router(monkeypatch, "refund_request")
    use_model(monkeypatch, [
        AIMessage(content="", tool_calls=[
            {"name": "post_refund", "args": {"order_no": "1260918430020004", "reason": "不喜欢"}, "id": "submit-1"},
            {"name": "post_refund", "args": {"order_no": "1260918430020005", "reason": "故障"}, "id": "submit-2"},
        ]),
        AIMessage(content="已提交申请 rq-1"),
    ])
    conversation_id = "11111111-1111-4111-8111-111111111111"
    create = AsyncMock(return_value=SimpleNamespace(
        request_key="rq-1", status=SimpleNamespace(value="pending"),
        conversation_id=conversation_id,
    ))
    monkeypatch.setattr(refund_tools, "create_refund_request", create)
    view = SimpleNamespace(
        request=SimpleNamespace(conversation_id=conversation_id, status=decision_status),
        approval=SimpleNamespace(comment="同意退款"),
    )
    lookup = AsyncMock(return_value=view)
    monkeypatch.setattr(nodes, "get_refund_request_for_user", lookup)
    ctx = SupportContext(4, conversation_id, Mock(spec=AsyncSession))
    graph = build_support_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": ctx.conversation_id}}
    chat = conversation_service.ConversationChat(graph)
    monkeypatch.setattr(conversation_service, "_require_conversation", AsyncMock())
    monkeypatch.setattr(conversation_service.conversation_repo, "touch_conversation", AsyncMock())
    turn = await chat.send_message(
        ctx.db, ctx.user_id, ctx.conversation_id, "请提交 1260918430020004 退款，原因不喜欢",
    )
    assert create.await_count == 1
    assert create.await_args.args == (ctx.db, ctx.user_id)
    assert create.await_args.kwargs["conversation_id"] == ctx.conversation_id
    assert create.await_args.kwargs["order_no"] in {"1260918430020004", "1260918430020005"}
    assert turn.status == "waiting_approval"
    assert turn.pending_request_key == "rq-1"
    state = (await graph.aget_state(config)).values
    assert state["messages"][2].tool_call_id == "submit-1"
    assert any("本轮已为订单" in message.text for message in state["messages"][2:4])
    assert state["pending_approval"] == "rq-1"
    assert graph.get_graph().nodes.get("wait_for_approval") is not None
    assert (await graph.aget_state(config)).next == ("wait_for_approval",)

    with pytest.raises(conversation_service.ConversationError, match="等待管理员审批"):
        await chat.send_message(ctx.db, ctx.user_id, ctx.conversation_id, "再发一条")
    assert await chat.resume_approval(ctx.db, ctx.user_id, ctx.conversation_id, "rq-1")
    assert not await chat.resume_approval(ctx.db, ctx.user_id, ctx.conversation_id, "rq-1")
    resumed = (await graph.aget_state(config)).values
    assert resumed["pending_approval"] is None
    assert expected in resumed["messages"][-1].text
    assert (await graph.aget_state(config)).next == ()
    create.assert_awaited_once()
    lookup.assert_awaited_once_with(ctx.db, ctx.user_id, "rq-1")


@pytest.mark.asyncio
async def test_existing_refund_from_another_conversation_does_not_pause(monkeypatch):
    mock_router(monkeypatch, "refund_request")
    use_model(monkeypatch, [
        AIMessage(content="", tool_calls=[{
            "name": "post_refund", "args": {"order_no": "1260918430020004", "reason": "不喜欢"}, "id": "submit-old",
        }]),
        AIMessage(content="这笔申请已在另一条会话中等待审批。"),
    ])
    monkeypatch.setattr(refund_tools, "create_refund_request", AsyncMock(return_value=SimpleNamespace(
        request_key="rq-old", status=SimpleNamespace(value="pending"),
        conversation_id="22222222-2222-4222-8222-222222222222",
    )))
    graph = build_support_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "11111111-1111-4111-8111-111111111111"}}
    result = await graph.ainvoke(
        {"messages": [("user", "申请退款")]}, config,
        context=SupportContext(4, config["configurable"]["thread_id"], Mock(spec=AsyncSession)),
    )
    assert result["pending_approval"] is None
    assert (await graph.aget_state(config)).next == ()


@pytest.mark.asyncio
async def test_parallel_tool_calls_share_session_without_overlapping_after_resume(monkeypatch):
    """模拟第二次运行恢复历史后，模型同时请求订单与退款工具。"""
    mock_router(monkeypatch, "order_query")
    model = use_model(monkeypatch, [
        AIMessage(content="有华硕和华为两台笔记本，你说的是哪台？"),
        AIMessage(content="", tool_calls=[
            {"name": "list_my_orders", "args": {}, "id": "orders-a"},
            {"name": "list_my_refunds", "args": {}, "id": "refunds-a"},
            {"name": "list_my_orders", "args": {}, "id": "orders-b"},
        ]),
        AIMessage(content="已核对华为笔记本的订单与退款记录。"),
    ])
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "resume-parallel-tools"}}
    await build_support_graph(checkpointer=saver).ainvoke(
        {"messages": [("user", "我的笔记本有问题")]}, config, context=context(),
    )

    # 新建图与业务会话，保留 checkpoint，模拟下一次执行脚本。
    resumed_context = context()
    active = 0
    completed = 0

    async def query(db, user_id, **kwargs):
        nonlocal active, completed
        assert db is resumed_context.db
        assert user_id == resumed_context.user_id
        assert active == 0, "同一个 AsyncSession 被多个工具并发使用"
        active += 1
        try:
            await asyncio.sleep(0.01)  # 模拟数据库等待，允许其他工具获得执行机会。
            completed += 1
            return [], 0
        finally:
            active -= 1

    monkeypatch.setattr(order_tools.order_service, "list_orders_for_user", query)
    monkeypatch.setattr(refund_tools.refund_service, "list_refund_requests_for_user", query)
    result = await build_support_graph(checkpointer=saver).ainvoke(
        {"messages": [("user", "华为")]}, config, context=resumed_context,
    )
    assert completed == 3
    assert {message.tool_call_id for message in result["messages"] if message.type == "tool"} == {
        "orders-a", "refunds-a", "orders-b",
    }
    assert [message.content for message in model.seen[1] if message.type == "human"] == [
        "我的笔记本有问题", "华为",
    ]
    assert result["messages"][-1].content == "已核对华为笔记本的订单与退款记录。"


@pytest.mark.asyncio
async def test_retrieved_sources_reach_agent_but_do_not_pollute_history(monkeypatch):
    mock_router(monkeypatch, "product_support", knowledge_question="X1 怎么开机？", product_model="X1")
    document = {
        "document_id": "manual-x1", "chunk_id": "start", "title": "X1 说明书",
        "source": "kb://manual-x1/start", "content": "首次使用需连接电源。",
    }

    async def fake_retrieval(state, runtime):
        return {"retrieved_documents": [document], "retrieval_status": "ready", "next_node": "support_agent"}

    monkeypatch.setattr(nodes, "retrieve_knowledge", fake_retrieval)
    model = use_model(monkeypatch, [AIMessage(content="请先连接电源。来源：X1 说明书")])
    result = await build_support_graph().ainvoke(
        {"messages": [("user", "X1 怎么开机？")]}, context=context(),
    )
    system_prompt = model.seen[0][0].content
    assert json.dumps(document, ensure_ascii=False) in system_prompt
    assert len(result["messages"]) == 2
    assert result["retrieved_documents"] == [document]
