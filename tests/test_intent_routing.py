"""路由协议与总图接线的离线测试，不调用真实模型或数据库。"""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from pydantic import ValidationError

from supportflow.agents.graph import nodes
from supportflow.agents.graph.builder import build_support_graph
from supportflow.agents.graph.context import SupportContext
from supportflow.agents.graph.state import initial_state
from supportflow.agents.structured_output.node_output import UnderstandAndRouteOutput


def mock_router(monkeypatch, intent, next_node):
    model = Mock()
    model.ainvoke = AsyncMock(return_value=UnderstandAndRouteOutput(
        intent=intent, next_node=next_node,
    ))
    monkeypatch.setattr(nodes, "_get_router_model", lambda: model)
    return model


@pytest.mark.parametrize("payload", [
    {"intent": "invented", "next_node": "clarify"},
    {"intent": "product_support", "next_node": "retrieve_knowledge"},
    {"intent": "order_query", "next_node": "end"},
    {"intent": "order_query", "nextnode": "order_agent"},
    {"intent": "order_query", "next_node": "order_agent", "user_id": 9},
])
def test_schema_rejects_invalid_or_extra_fields(payload):
    with pytest.raises(ValidationError):
        UnderstandAndRouteOutput.model_validate(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("intent,suggestion,confirmed,expected", [
    ("order_query", "refund_agent", False, "order_agent"),
    ("refund_query", "order_agent", False, "refund_agent"),
    ("refund_request", "refund_agent", False, "order_agent"),
    ("refund_request", "refund_agent", True, "refund_agent"),
    ("refund_request", "order_agent", True, "order_agent"),
    ("refund_request", "clarify", True, "clarify"),
    ("policy_question", "refund_agent", True, "prepare_knowledge"),
    ("product_support", "order_agent", False, "order_agent"),
    ("unknown", "refund_agent", True, "clarify"),
])
async def test_business_entry_constraints(monkeypatch, intent, suggestion, confirmed, expected):
    mock_router(monkeypatch, intent, suggestion)
    state = initial_state()
    state["messages"] = [HumanMessage(content="本轮问题")]
    state["order"]["candidate_order_nos"] = ["A1004"]
    if confirmed:
        state["order"]["selected_order_no"] = "A1004"
    before = deepcopy(state)
    result = await nodes.understand_and_route(
        state, Runtime(context=SupportContext(4, "route-test")),
    )
    assert result["next_node"] == expected
    assert result["current_intent"] == intent
    assert "messages" not in result and "message" not in result
    assert state == before


@pytest.mark.asyncio
async def test_history_and_progress_are_sent_without_resetting_refund(monkeypatch):
    model = mock_router(monkeypatch, "policy_question", "prepare_knowledge")
    state = initial_state()
    state["refund"].update(phase="need_reason", order_no="A1004")
    state["messages"] = [
        HumanMessage(content="我要退 A1004"),
        AIMessage(content="退款原因是什么？"),
        HumanMessage(content="先问一下运费谁承担？"),
    ]
    result = await nodes.understand_and_route(
        state, Runtime(context=SupportContext(4, "route-test")),
    )
    sent = model.ainvoke.await_args.args[0]
    assert isinstance(sent[0], SystemMessage)
    assert '"phase": "need_reason"' in sent[1].content
    assert sent[2:] == state["messages"]
    assert "refund" not in result
    assert result["knowledge"]["topic"] == "policy"
    assert result["retrieved_documents"] == []


@pytest.mark.asyncio
async def test_new_conversation_initializes_missing_state(monkeypatch):
    mock_router(monkeypatch, "refund_request", "refund_agent")
    result = await nodes.understand_and_route(
        {"messages": [HumanMessage(content="我要退款")]},
        Runtime(context=SupportContext(4, "route-test")),
    )
    assert result["order"]["purpose"] == "refund"
    assert result["refund"] == initial_state()["refund"]
    assert result["next_node"] == "order_agent"


@pytest.mark.asyncio
async def test_empty_history_does_not_call_model(monkeypatch):
    model = mock_router(monkeypatch, "unknown", "clarify")
    with pytest.raises(ValueError, match="messages"):
        await nodes.understand_and_route(
            initial_state(), Runtime(context=SupportContext(4, "route-test")),
        )
    model.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_routes_once_and_keeps_checkpoint_history(monkeypatch):
    model = mock_router(monkeypatch, "refund_request", "refund_agent")
    visited = []

    async def fake_order(state, runtime):
        visited.append("order")
        assert runtime.context.user_id == 4
        return {
            "next_node": "end",
            "messages": [AIMessage(content="请提供商品或订单号")],
        }

    async def fake_refund(state, runtime):
        visited.append("refund")
        return {"messages": [AIMessage(content="退款记录")], "next_node": "end"}

    monkeypatch.setattr(nodes, "order_agent", fake_order)
    monkeypatch.setattr(nodes, "refund_agent", fake_refund)
    graph = build_support_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "route-test"}}
    context = SupportContext(4, "route-test")
    await graph.ainvoke(
        {"messages": [HumanMessage(content="我要退款")]}, config, context=context,
    )
    model.ainvoke.return_value = UnderstandAndRouteOutput(
        intent="refund_query", next_node="refund_agent",
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="先看看我的退款记录")]}, config, context=context,
    )
    assert visited == ["order", "refund"]
    assert len(result["messages"]) == 4
    assert result["messages"][-1].content == "退款记录"
    assert result["current_intent"] == "refund_query"
