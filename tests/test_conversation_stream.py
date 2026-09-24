"""真实图、DeepSeek 适配器和 SSE 路由的离线联调，不连接外部服务。"""

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.graph.builder import build_support_graph
from supportflow.api.auth.deps import require_customer
from supportflow.api.customer.conversations import router
from supportflow.db.session import get_db
from supportflow.services import conversations


class ModelStream(httpx.AsyncByteStream):
    def __init__(self, deltas, *, continue_after_first=None):
        self.deltas = deltas
        self.continue_after_first = continue_after_first

    async def __aiter__(self):
        for index, delta in enumerate(self.deltas):
            if index == 1 and self.continue_after_first is not None:
                await self.continue_after_first.wait()
            packet = {
                "id": "offline-completion", "object": "chat.completion.chunk",
                "created": 0, "model": "deepseek-chat",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            yield f"data: {json.dumps(packet)}\n\n".encode()
        yield b"data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_nested_agent_reaches_sse_before_completion_and_saves_only_chat(monkeypatch):
    first_delta_delivered = asyncio.Event()
    model_calls = []

    def respond(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        is_router = any(
            tool["function"]["name"] == "UnderstandAndRouteOutput"
            for tool in payload.get("tools", [])
        )
        model_calls.append("router" if is_router else "agent")
        if is_router:
            stream = ModelStream([{"tool_calls": [{
                "index": 0, "id": "route-1", "type": "function",
                "function": {
                    "name": "UnderstandAndRouteOutput",
                    "arguments": json.dumps({"intent": "unknown"}),
                },
            }]}])
        else:
            stream = ModelStream(
                [{"content": text} for text in ("你", "好", "！")],
                continue_after_first=first_delta_delivered,
            )
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, stream=stream,
        )

    db = Mock(spec=AsyncSession)
    monkeypatch.setattr(
        conversations.conversation_repo, "get_conversation_for_user",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(conversations.conversation_repo, "touch_conversation", AsyncMock())
    graph = build_support_graph(checkpointer=InMemorySaver())
    chat = conversations.ConversationChat(graph)
    app = FastAPI()
    app.include_router(router, prefix="/customer")
    app.state.conversation_chat = chat
    app.dependency_overrides[require_customer] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: db

    conversation_id = str(uuid4())
    body = json.dumps({"content": "hello"}).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": f"/customer/conversations/{conversation_id}/messages/stream",
        "query_string": b"", "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1), "server": ("test", 80),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body":
            if b"event: delta" in message.get("body", b""):
                first_delta_delivered.set()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = ChatDeepSeek(
            model="deepseek-chat", api_key="offline-test",
            http_async_client=client, max_retries=0,
        )
        monkeypatch.setitem(
            sys.modules, "supportflow.agents.llm", SimpleNamespace(chat_model=model),
        )
        # 如果先攒完整回答再发送，模型与 SSE 会互相等待，测试将超时。
        await asyncio.wait_for(app(scope, receive, send), timeout=10)

    start = next(item for item in sent if item["type"] == "http.response.start")
    assert start["status"] == 200
    assert dict(start["headers"])[b"content-type"].startswith(b"text/event-stream")
    wire = b"".join(item.get("body", b"") for item in sent).decode()
    texts = [json.loads(line[6:])["text"] for line in wire.splitlines() if line.startswith("data: ")]
    assert texts == ["你", "好", "！"]
    assert model_calls == ["router", "agent"]

    snapshot = await graph.aget_state({"configurable": {"thread_id": conversation_id}})
    history = conversations._public_messages(snapshot.values["messages"])
    assert [(message.role, message.content) for message in history] == [
        ("user", "hello"), ("assistant", "你好！"),
    ]
    assert snapshot.values["current_intent"] == "unknown"
    assert len(snapshot.values["messages"]) == 2
    assert not chat._running
