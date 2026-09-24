"""混合召回和图节点的离线集成测试，不调用真实模型和数据库。"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from langgraph.runtime import Runtime

from supportflow.agents.graph import nodes
from supportflow.agents.graph.state import initial_state
from supportflow.retrieval.retrieving import hybrid
from supportflow.retrieval.types import RetrievalUnavailable


def chunk(chunk_id):
    return {
        "document_id": "manual", "chunk_id": chunk_id, "title": "使用指南",
        "section": "连接", "source": "data/manual.md", "category": "data",
        "content": f"片段 {chunk_id} 的正文", "score": 0.8,
    }


@pytest.fixture
def recalls(monkeypatch):
    vector = AsyncMock(return_value=[chunk("vector"), chunk("shared")])
    bm25 = AsyncMock(return_value=[chunk("bm25"), chunk("shared")])
    monkeypatch.setattr(hybrid, "retrieve_vector", vector)
    monkeypatch.setattr(hybrid, "retrieve_bm25", bm25)
    return vector, bm25


@pytest.fixture(autouse=True)
def reranker(monkeypatch):
    """重排会调百炼的外部接口，这里统一换成「原样返回前 top_n 条」。

    autouse：图节点默认开着重排，任何一条走到真实 retrieve_hybrid 的用例
    都会打网络，必须把外部调用挡在测试之外。
    """
    async def passthrough(query, chunks, *, top_n):
        return chunks[:top_n]

    mock = AsyncMock(side_effect=passthrough)
    monkeypatch.setattr(hybrid, "rerank_chunks", mock)
    return mock


@pytest.mark.asyncio
async def test_recall_window_filters_and_fusion(recalls):
    result = await hybrid.retrieve_hybrid(
        " 问题 ", top_k=1, candidate_k=10, rrf_k=10, min_score=0.6,
        category="data", document_ids=["manual"],
    )
    assert [item["chunk_id"] for item in result] == ["shared"]
    assert result[0]["score"] == pytest.approx(2 / 12)
    recalls[0].assert_awaited_once_with(
        "问题", top_k=10, min_score=0.6, category="data", document_ids=["manual"],
    )
    recalls[1].assert_awaited_once_with("问题", top_k=10, category="data", document_ids=["manual"])


@pytest.mark.asyncio
async def test_two_recalls_run_concurrently(recalls):
    vector_started = asyncio.Event()
    bm25_started = asyncio.Event()

    async def vector(*args, **kwargs):
        vector_started.set()
        await bm25_started.wait()
        return [chunk("shared")]

    async def bm25(*args, **kwargs):
        bm25_started.set()
        await vector_started.wait()
        return [chunk("shared")]

    recalls[0].side_effect = vector
    recalls[1].side_effect = bm25
    result = await asyncio.wait_for(hybrid.retrieve_hybrid("问题"), timeout=2)
    assert result[0]["score"] == pytest.approx(2 / 61)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [0, 1])
async def test_one_failed_route_uses_other_results_and_logs_safely(recalls, caplog, failed):
    recalls[failed].side_effect = RetrievalUnavailable("private transport details")
    result = await hybrid.retrieve_hybrid("问题")
    assert len(result) == 2
    assert result[0]["score"] == pytest.approx(1 / 61)
    assert "召回不可用" in caplog.text
    assert "private" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [0, 1])
async def test_one_empty_route_uses_other_results(recalls, empty):
    recalls[empty].return_value = []
    result = await hybrid.retrieve_hybrid("问题")
    assert len(result) == 2
    assert result[0]["score"] == pytest.approx(1 / 61)


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [(0,), (1,), (0, 1)])
async def test_failure_without_any_candidates_is_unavailable(recalls, failures):
    for index, recall in enumerate(recalls):
        recall.return_value = []
        if index in failures:
            recall.side_effect = RetrievalUnavailable("private failure")
    with pytest.raises(RetrievalUnavailable) as error:
        await hybrid.retrieve_hybrid("问题")
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_both_empty_return_empty(recalls):
    for recall in recalls:
        recall.return_value = []
    assert await hybrid.retrieve_hybrid("问题") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"query": " "}, {"query": "q", "top_k": 0}, {"query": "q", "top_k": True},
    {"query": "q", "candidate_k": 4}, {"query": "q", "candidate_k": 101},
    {"query": "q", "candidate_k": 20.5}, {"query": "q", "candidate_k": True},
    {"query": "q", "rrf_k": 0}, {"query": "q", "rrf_k": 1.5},
    {"query": "q", "min_score": float("nan")}, {"query": "q", "min_score": 1.1},
    {"query": "q", "category": "other"}, {"query": "q", "document_ids": [""]},
])
async def test_invalid_options_do_not_call_recalls(recalls, kwargs):
    with pytest.raises(ValueError):
        await hybrid.retrieve_hybrid(**kwargs)
    for recall in recalls:
        recall.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_empty_document_filter_skips_both_routes(recalls):
    assert await hybrid.retrieve_hybrid("问题", document_ids=[]) == []
    for recall in recalls:
        recall.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_unexpected_errors_and_cancellation_are_not_swallowed(recalls, error_type):
    recalls[0].side_effect = error_type("stop")
    with pytest.raises(error_type):
        await hybrid.retrieve_hybrid("问题")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["fused", "degraded", "empty", "unavailable"])
async def test_graph_node_uses_real_hybrid_entrypoint(recalls, reranker, outcome):
    if outcome in ("empty", "unavailable"):
        for recall in recalls:
            recall.return_value = []
    if outcome in ("degraded", "unavailable"):
        recalls[0].side_effect = RetrievalUnavailable("offline")
    state = initial_state()
    state["knowledge"] = {"question": "如何连接？", "product_model": "X1"}
    state["retrieved_documents"] = [chunk("old")]
    result = await nodes.retrieve_knowledge(state, Runtime())
    expected_status = "ready" if outcome in ("fused", "degraded") else outcome
    assert result["retrieval_status"] == expected_status
    assert result["next_node"] == "support_agent"
    assert all(item["chunk_id"] != "old" for item in result["retrieved_documents"])
    if outcome == "fused":
        assert result["retrieved_documents"][0]["chunk_id"] == "shared"
        assert result["retrieved_documents"][0]["score"] == pytest.approx(2 / 62)
        # 节点默认开着重排：融合出的候选要真的送进重排，再拿重排的结果当本轮证据。
        reranker.assert_awaited_once()
        assert reranker.await_args.args[0] == "商品型号：X1\n问题：如何连接？"
    if outcome in ("empty", "unavailable"):
        assert result["retrieved_documents"] == []
    assert state["retrieved_documents"] == [chunk("old")]
    for recall in recalls:
        assert recall.await_args.args == ("商品型号：X1\n问题：如何连接？",)
