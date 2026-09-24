"""向量召回的离线测试：过滤、排序、只读查询和外部失败。"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pymilvus import DataType

from supportflow.retrieval.retrieving import vector


def hit(chunk_id="DOC#1", score=0.8):
    return {"distance": score, "entity": {
        "chunk_id": chunk_id, "document_id": "DOC", "title": "使用指南",
        "section": "开机", "source": "data/DOC.md", "category": "data", "content": "长按开机键。",
    }}


@pytest.fixture
def client(monkeypatch):
    config = SimpleNamespace(
        MILVUS_URI="http://example.invalid:19530", DB_NAME="test", COLLECTION="docs",
        EMBEDDING_DIM=2, EMBEDDING_MODEL="test-embedding",
    )
    monkeypatch.setitem(sys.modules, "supportflow.core.config", SimpleNamespace(settings=config))
    client = Mock()
    client.has_collection.return_value = True
    client.describe_collection.return_value = {"fields": [
        {"name": "vector", "type": DataType.FLOAT_VECTOR, "params": {"dim": 2}},
    ]}
    client.search.return_value = [[hit()]]
    monkeypatch.setattr(vector, "MilvusClient", Mock(return_value=client))
    monkeypatch.setattr(vector, "embed_query", AsyncMock(return_value=[0.2, 0.8]))
    return client


@pytest.mark.asyncio
async def test_retrieval_returns_ranked_deduplicated_sources(client):
    client.search.return_value = [[hit("low", 0.49), hit("second", 0.5), hit("first", 0.9), hit("first", 0.8)]]
    documents = await vector.retrieve(" 怎么开机？ ", top_k=4)
    assert [doc["chunk_id"] for doc in documents] == ["first", "second"]
    assert documents[0]["content"] == "长按开机键。"
    assert documents[0]["source"] == "data/DOC.md"
    assert documents[0]["score"] == 0.9
    vector.embed_query.assert_awaited_once_with("怎么开机？")
    args = client.search.call_args.kwargs
    assert args["limit"] == 4
    assert args["anns_field"] == "vector"
    assert args["search_params"]["metric_type"] == "COSINE"
    assert 'embedding_model == "test-embedding"' in args["filter"]
    assert 'embedding_dim == 2' in args["filter"]
    client.close.assert_called_once()
    client.create_database.assert_not_called()
    client.create_collection.assert_not_called()
    client.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_filter_values_are_escaped(client):
    ids = ['文档" or chunk_id != "', '目录\\资料']
    await vector.retrieve("退款期限", category="policies", document_ids=ids)
    expression = client.search.call_args.kwargs["filter"]
    assert 'category == "policies"' in expression
    serialized_ids = expression.split("document_id in ")[1]
    assert json.loads(serialized_ids) == ids


@pytest.mark.asyncio
@pytest.mark.parametrize("results", [[], [[]], [[hit(score=0.1)]], [[hit(score=float("nan"))]]])
async def test_no_qualifying_hits_return_empty(client, results):
    client.search.return_value = results
    assert await vector.retrieve("库外问题") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"query": " "}, {"query": "q", "top_k": 0}, {"query": "q", "top_k": 101},
    {"query": "q", "min_score": float("nan")}, {"query": "q", "min_score": 1.1},
    {"query": "q", "category": "other"}, {"query": "q", "document_ids": [""]},
])
async def test_invalid_parameters_do_not_call_external_services(client, kwargs):
    with pytest.raises(ValueError):
        await vector.retrieve(**kwargs)
    vector.embed_query.assert_not_awaited()
    vector.MilvusClient.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_empty_document_filter_does_not_search_entire_collection(client):
    assert await vector.retrieve("q", document_ids=[]) == []
    vector.embed_query.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["missing_collection", "schema", "search", "metadata"])
async def test_milvus_errors_are_unavailable_and_close_client(client, stage):
    if stage == "missing_collection":
        client.has_collection.return_value = False
    elif stage == "schema":
        client.describe_collection.return_value["fields"][0]["params"]["dim"] = 3
    elif stage == "search":
        client.search.side_effect = TimeoutError("simulated timeout")
    else:
        del client.search.return_value[0][0]["entity"]["source"]
    with pytest.raises(vector.RetrievalUnavailable):
        await vector.retrieve("q")
    client.close.assert_called_once()
    client.create_collection.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_failure_is_unavailable(client):
    vector.embed_query.side_effect = TimeoutError("sensitive transport details")
    with pytest.raises(vector.RetrievalUnavailable) as error:
        await vector.retrieve("q")
    assert "sensitive" not in str(error.value)
    vector.MilvusClient.assert_not_called()


@pytest.mark.asyncio
# ⚠️ 参数名不能叫 vector：本文件顶部 `from ... import vector` 拿的是模块，
# pytest 会按参数名注入，撞名后函数里的 vector 就变成 list 了（MilvusClient 全没了）。
@pytest.mark.parametrize("bad_embedding", [[1.0], [float("inf"), 1.0], [0.0, 0.0]])
async def test_bad_query_vectors_do_not_connect(client, bad_embedding):
    vector.embed_query.return_value = bad_embedding
    with pytest.raises(vector.RetrievalUnavailable):
        await vector.retrieve("q")
    vector.MilvusClient.assert_not_called()
