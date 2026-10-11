"""联网搜索使用模拟 HTTP，不访问互联网，不初始化真实模型。"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr

from supportflow.agents.tools import web_search


@pytest.fixture
def settings(monkeypatch):
    from supportflow.core import config

    settings = SimpleNamespace(
        TAVILY_API_KEY=SecretStr("offline-search-key"),
        TAVILY_BASE_URL="https://search.example/",
        WEB_SEARCH_MAX_RESULTS=2,
        WEB_SEARCH_TIMEOUT_SECONDS=10,
    )
    monkeypatch.setattr(config, "settings", settings)
    return settings


def mock_transport(monkeypatch, handler):
    client_factory = httpx.AsyncClient
    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **kwargs: client_factory(
        **kwargs, transport=httpx.MockTransport(handler),
    ))


@pytest.mark.asyncio
async def test_search_sends_config_and_returns_bounded_actual_sources(monkeypatch, settings):
    def respond(request):
        assert str(request.url) == "https://search.example/search"
        assert request.headers["Authorization"] == "Bearer offline-search-key"
        assert json.loads(request.content) == {
            "query": "X1 如何开机", "topic": "general", "search_depth": "basic",
            "max_results": 2, "include_answer": False, "include_raw_content": False,
        }
        return httpx.Response(200, json={"answer": "不采用服务生成的答案", "results": [
            {"title": "官方说明", "url": "https://support.example/x1", "content": "摘要" * 3000},
            {"title": "重复", "url": "https://support.example/x1", "content": "重复摘要"},
            {"title": "危险链接", "url": "javascript:alert(1)", "content": "不采用"},
            {"title": "没有正文", "url": "https://empty.example", "content": ""},
            {"title": "另一个来源", "url": "https://other.example", "content": "另一条摘要"},
            {"title": "超出上限", "url": "https://extra.example", "content": "超限"},
        ]})

    mock_transport(monkeypatch, respond)
    result = await web_search.search_web("  X1 如何开机 ")
    assert len(result) == 2
    assert [source["url"] for source in result] == ["https://support.example/x1", "https://other.example"]
    assert len(result[0]["content"]) == 4000


@pytest.mark.asyncio
async def test_missing_api_key_and_empty_query_never_create_client(monkeypatch, settings):
    settings.TAVILY_API_KEY = SecretStr(" ")
    client = Mock(side_effect=AssertionError("未配置不能请求网络"))
    monkeypatch.setattr(web_search.httpx, "AsyncClient", client)
    with pytest.raises(web_search.WebSearchUnavailable, match="未配置"):
        await web_search.search_web("如何开机")
    with pytest.raises(ValueError, match="不能为空"):
        await web_search.search_web(" ")
    client.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload", [
    (401, {"detail": "offline-search-key"}),
    (429, {"detail": "配额不足"}),
    (500, {"detail": "服务器错误"}),
    (200, {}),
    (200, {"results": None}),
    (200, {"results": {"url": "错误结构"}}),
])
async def test_service_failures_are_sanitized(monkeypatch, settings, status, payload):
    mock_transport(monkeypatch, lambda request: httpx.Response(status, json=payload))
    with pytest.raises(web_search.WebSearchUnavailable) as exc:
        await web_search.search_web("如何开机")
    assert "offline-search-key" not in str(exc.value)


@pytest.mark.asyncio
async def test_empty_search_and_malformed_entries_are_not_online_evidence(monkeypatch, settings):
    mock_transport(monkeypatch, lambda request: httpx.Response(200, json={"results": [
        None, "网页", {"title": "无地址", "content": "摘要"},
        {"title": "凭据链接", "url": "https://user:secret@support.example", "content": "摘要"},
    ]}))
    assert await web_search.search_web("如何开机") == []


@pytest.mark.asyncio
async def test_timeout_becomes_unavailable(monkeypatch, settings):
    def timeout(request):
        raise httpx.ReadTimeout("带有请求敏感数据的异常", request=request)

    mock_transport(monkeypatch, timeout)
    with pytest.raises(web_search.WebSearchUnavailable, match="ReadTimeout") as exc:
        await web_search.search_web("如何开机")
    assert "敏感数据" not in str(exc.value)


@pytest.mark.asyncio
async def test_invalid_provider_url_degrades_without_exposing_config(monkeypatch, settings):
    settings.TAVILY_BASE_URL = "https://example.invalid:invalid-port"
    mock_transport(monkeypatch, lambda request: pytest.fail("无效地址不应发送请求"))
    with pytest.raises(web_search.WebSearchUnavailable, match="InvalidURL") as exc:
        await web_search.search_web("如何开机")
    assert "invalid-host" not in str(exc.value)
