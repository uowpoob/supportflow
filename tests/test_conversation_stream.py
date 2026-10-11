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
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.agents.graph.builder import build_support_graph
from supportflow.api.auth.deps import require_customer
from supportflow.api.customer.conversations import router
from supportflow.db.session import get_db
from supportflow.services import conversations
from supportflow.services.conversations import ConversationError
from supportflow.schemas.conversations import ActiveTurnOut, ChatMessageOut


@pytest.fixture(autouse=True)
def worker_database(monkeypatch):
    """后台任务单独用一个数据库会话；离线测试不打开真实连接。"""
    worker = Mock(spec=AsyncSession)
    factory = Mock(return_value=worker)
    monkeypatch.setattr(conversations, "SessionLocal", factory)
    monkeypatch.setattr(
        conversations.ConversationChat, "_maybe_generate_title", AsyncMock(return_value=None),
    )
    return factory, worker


class RecoverableGraph:
    """第一段不会写入 checkpoint，模拟刷新发生在图节点执行期间。"""

    def __init__(self, *, failure=False):
        self.values = {"messages": []}
        self.continue_run = asyncio.Event()
        self.waiting = asyncio.Event()
        self.closed = asyncio.Event()
        self.failure = failure
        self.context = None

    async def aget_state(self, *_args):
        return SimpleNamespace(values=dict(self.values))

    async def astream(self, state, *_args, context, **_kwargs):
        self.context = context
        message = state["messages"][0]
        try:
            yield {"type": "messages", "data": (
                AIMessageChunk(id="reply-1", content="部分"), {"langgraph_node": "model"},
            )}
            self.waiting.set()
            await self.continue_run.wait()
            if self.failure:
                raise RuntimeError("offline graph failure")
            yield {"type": "messages", "data": (
                AIMessageChunk(id="reply-1", content="回复"), {"langgraph_node": "model"},
            )}
            self.values = {
                "messages": [message, AIMessage(id="reply-1", content="部分回复")],
                "retrieval_status": "empty",
                "retrieved_documents": [],
            }
        finally:
            self.closed.set()


def allow_conversation(monkeypatch):
    monkeypatch.setattr(
        conversations.conversation_repo, "get_conversation_for_user",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(conversations.conversation_repo, "touch_conversation", AsyncMock())


async def finish_worker(chat, graph):
    tasks = tuple(chat._tasks)
    graph.continue_run.set()
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)


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
    frames = [frame for frame in wire.replace("\r\n", "\n").split("\n\n") if frame]
    texts = [
        json.loads(line[6:])["text"]
        for frame in frames if "event: delta" in frame
        for line in frame.splitlines() if line.startswith("data: ")
    ]
    assert texts == ["你", "好", "！"]
    assert any("event: done" in frame for frame in frames)
    assert model_calls == ["router", "agent"]

    snapshot = await graph.aget_state({"configurable": {"thread_id": conversation_id}})
    history = conversations._public_messages(snapshot.values["messages"])
    assert [(message.role, message.content) for message in history] == [
        ("user", "hello"), ("assistant", "你好！"),
    ]
    assert snapshot.values["current_intent"] == "unknown"
    assert len(snapshot.values["messages"]) == 2
    assert not chat._running


@pytest.mark.asyncio
async def test_stream_failure_after_delta_emits_error_event():
    class FailingChat:
        async def stream_turn(self, *_args):
            yield "部分回复"
            raise ConversationError("请先核对历史和退款状态", status_code=502)

    app = FastAPI()
    app.include_router(router, prefix="/customer")
    app.state.conversation_chat = FailingChat()
    app.dependency_overrides[require_customer] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: Mock(spec=AsyncSession)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post(
            f"/customer/conversations/{uuid4()}/messages/stream",
            json={"content": "申请退款"},
        )

    assert response.status_code == 200
    frames = [frame for frame in response.text.replace("\r\n", "\n").split("\n\n") if frame]
    assert "event: delta" in frames[0]
    assert "event: error" in frames[1]
    payload = json.loads(next(line[6:] for line in frames[1].splitlines() if line.startswith("data: ")))
    assert payload == {"status": 502, "message": "请先核对历史和退款状态"}
    assert not any("event: done" in frame for frame in frames)


@pytest.mark.asyncio
async def test_history_exposes_waiting_state_for_recovery(monkeypatch):
    monkeypatch.setattr(
        conversations.conversation_repo, "get_conversation_for_user",
        AsyncMock(return_value=SimpleNamespace()),
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(
        values={"messages": [], "pending_approval": "rq-1"},
    )))
    chat = conversations.ConversationChat(graph)
    page = await chat.list_messages(Mock(spec=AsyncSession), 1, str(uuid4()), 0, 100)

    assert page.status == "waiting_approval"
    assert page.pending_request_key == "rq-1"


@pytest.mark.asyncio
async def test_closing_customer_stream_keeps_worker_and_restores_history(
    monkeypatch, worker_database,
):
    allow_conversation(monkeypatch)
    graph = RecoverableGraph()
    chat = conversations.ConversationChat(graph)
    db = Mock(spec=AsyncSession)
    conversation_id = str(uuid4())
    stream = chat.stream_turn(db, 1, conversation_id, "你好")
    assert await anext(stream) == "部分"
    await asyncio.wait_for(graph.waiting.wait(), timeout=2)
    await stream.aclose()

    assert not graph.closed.is_set()
    assert conversation_id in chat._running
    assert len(chat._tasks) == 1
    factory, worker = worker_database
    factory.assert_called_once_with()
    assert graph.context.db is worker
    assert graph.context.db is not db
    worker.close.assert_not_awaited()

    page = await chat.list_messages(db, 1, conversation_id, 0, 100)
    assert page.running
    assert page.items == []
    assert page.total == 0
    assert page.active_turn.user_message.content == "你好"
    assert page.active_turn.user_message.role == "user"
    assert page.active_turn.assistant_text == "部分"
    assert page.run_error is None
    # API 返回的是副本，之后的后台追加不会修改已经返回的响应。
    page.active_turn.assistant_text = "客户端副本"
    recovered = await chat.list_messages(db, 1, conversation_id, 0, 100)
    assert recovered.active_turn.assistant_text == "部分"

    with pytest.raises(ConversationError) as busy:
        await chat.send_message(db, 1, conversation_id, "重复发送")
    assert busy.value.status_code == 409

    await finish_worker(chat, graph)
    assert graph.closed.is_set()
    assert not chat._running
    assert not chat._tasks
    worker.close.assert_awaited_once()
    final = await chat.list_messages(db, 1, conversation_id, 0, 100)
    assert not final.running
    assert final.active_turn is None
    assert final.total == 2
    assert [(item.role, item.content) for item in final.items] == [
        ("user", "你好"), ("assistant", "部分回复"),
    ]
    assert final.items[0].id == recovered.active_turn.user_message.id
    assert final.retrieval_status == "empty"
    assert final.retrieved_sources == []
    assert final.run_error is None
    paged = await chat.list_messages(db, 1, conversation_id, 1, 1)
    assert paged.total == 2
    assert [item.content for item in paged.items] == ["部分回复"]


@pytest.mark.asyncio
async def test_cancelling_customer_stream_does_not_cancel_worker(monkeypatch, worker_database):
    allow_conversation(monkeypatch)
    graph = RecoverableGraph()
    chat = conversations.ConversationChat(graph)
    conversation_id = str(uuid4())
    stream = chat.stream_turn(Mock(spec=AsyncSession), 1, conversation_id, "你好")
    assert await anext(stream) == "部分"
    await asyncio.wait_for(graph.waiting.wait(), timeout=2)
    next_item = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    next_item.cancel()
    with pytest.raises(asyncio.CancelledError):
        await next_item

    assert conversation_id in chat._running
    assert not graph.closed.is_set()
    assert not next(iter(chat._tasks)).cancelled()
    await finish_worker(chat, graph)
    history = await chat.list_messages(Mock(spec=AsyncSession), 1, conversation_id, 0, 100)
    assert not history.running
    assert [item.content for item in history.items] == ["你好", "部分回复"]
    worker_database[1].close.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_disconnected_worker_exposes_error_without_retry(monkeypatch, worker_database):
    allow_conversation(monkeypatch)
    graph = RecoverableGraph(failure=True)
    chat = conversations.ConversationChat(graph)
    conversation_id = str(uuid4())
    stream = chat.stream_turn(Mock(spec=AsyncSession), 1, conversation_id, "你好")
    assert await anext(stream) == "部分"
    await stream.aclose()
    await finish_worker(chat, graph)

    history = await chat.list_messages(Mock(spec=AsyncSession), 1, conversation_id, 0, 100)
    assert not history.running
    assert history.active_turn is None
    assert history.run_error == conversations.TURN_FAILURE
    assert graph.closed.is_set()
    assert not chat._tasks
    worker_database[0].assert_called_once_with()
    worker_database[1].close.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_startup_failure_releases_lock(monkeypatch, worker_database):
    allow_conversation(monkeypatch)
    graph = SimpleNamespace(aget_state=AsyncMock(side_effect=RuntimeError("checkpoint unavailable")))
    chat = conversations.ConversationChat(graph)
    conversation_id = str(uuid4())
    stream = chat.stream_turn(Mock(spec=AsyncSession), 1, conversation_id, "你好")
    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        await anext(stream)
    assert not chat._running
    assert not chat._active_turns
    assert not chat._tasks
    worker_database[0].assert_not_called()


@pytest.mark.asyncio
async def test_cancelling_stream_during_startup_releases_lock(monkeypatch, worker_database):
    allow_conversation(monkeypatch)
    entered = asyncio.Event()

    async def checkpoint(*_args):
        entered.set()
        await asyncio.Event().wait()

    chat = conversations.ConversationChat(SimpleNamespace(aget_state=checkpoint))
    conversation_id = str(uuid4())
    stream = chat.stream_turn(Mock(spec=AsyncSession), 1, conversation_id, "你好")
    startup = asyncio.create_task(anext(stream))
    await asyncio.wait_for(entered.wait(), timeout=2)
    startup.cancel()
    with pytest.raises(asyncio.CancelledError):
        await startup
    assert not chat._running
    assert not chat._active_turns
    assert not chat._tasks
    worker_database[0].assert_not_called()


@pytest.mark.asyncio
async def test_history_checks_ownership_before_checkpoint_or_running_state(monkeypatch):
    monkeypatch.setattr(
        conversations.conversation_repo, "get_conversation_for_user", AsyncMock(return_value=None),
    )
    graph = SimpleNamespace(aget_state=AsyncMock())
    chat = conversations.ConversationChat(graph)
    conversation_id = str(uuid4())
    chat._running.add(conversation_id)
    with pytest.raises(ConversationError) as denied:
        await chat.list_messages(Mock(spec=AsyncSession), 2, conversation_id, 0, 100)
    assert denied.value.status_code == 404
    graph.aget_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_rereads_final_checkpoint_when_worker_finishes_during_read(monkeypatch):
    allow_conversation(monkeypatch)
    conversation_id = str(uuid4())
    old_snapshot = SimpleNamespace(values={"messages": []})
    final_snapshot = SimpleNamespace(values={"messages": [
        HumanMessage(id="question-1", content="你好"), AIMessage(id="reply-1", content="已完成"),
    ]})
    reads = 0

    async def read_checkpoint(*_args):
        nonlocal reads
        reads += 1
        if reads == 1:
            # 第一次读取拿到旧版本时，后台任务已经提交完并释放执行锁。
            chat._running.discard(conversation_id)
            chat._active_turns.pop(conversation_id, None)
            return old_snapshot
        return final_snapshot

    chat = conversations.ConversationChat(SimpleNamespace(aget_state=read_checkpoint))
    chat._running.add(conversation_id)
    chat._active_turns[conversation_id] = ActiveTurnOut(
        user_message=ChatMessageOut(id="question-1", role="user", content="你好"),
        assistant_text="已",
    )
    history = await chat.list_messages(Mock(spec=AsyncSession), 1, conversation_id, 0, 100)
    assert reads == 2
    assert not history.running
    assert history.active_turn is None
    assert [item.content for item in history.items] == ["你好", "已完成"]


@pytest.mark.asyncio
async def test_history_hides_draft_already_saved_in_checkpoint(monkeypatch):
    allow_conversation(monkeypatch)
    conversation_id = str(uuid4())
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={"messages": [
        HumanMessage(id="question-1", content="你好"), AIMessage(id="reply-1", content="已完成"),
    ]})))
    chat = conversations.ConversationChat(graph)
    chat._running.add(conversation_id)
    chat._active_message_ids[conversation_id] = "reply-1"
    chat._active_turns[conversation_id] = ActiveTurnOut(
        user_message=ChatMessageOut(id="question-1", role="user", content="你好"),
        assistant_text="已完成",
    )
    history = await chat.list_messages(Mock(spec=AsyncSession), 1, conversation_id, 0, 100)
    assert history.running
    assert len(history.items) == history.total == 2
    assert history.active_turn.assistant_text == ""
    assert chat._active_turns[conversation_id].assistant_text == "已完成"
