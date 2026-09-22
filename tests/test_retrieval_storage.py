"""验证重复入库、坏向量拒写和失败时的客户端释放，不访问外部服务。"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.documents import Document
from pydantic import SecretStr

from supportflow.retrieval import embedding, milvus, resource2chunks


@pytest.fixture
def settings(monkeypatch):
    settings = SimpleNamespace(
        COLLECTION="test_documents", EMBEDDING_DIM=2, EMBEDDING_MODEL="offline-test",
        DASHSCOPE_API_KEY=SecretStr("offline-test-key"),
    )
    monkeypatch.setitem(sys.modules, "supportflow.core.config", SimpleNamespace(settings=settings))
    return settings


def chunk(index=1, content="原始条款"):
    return Document(page_content=content, metadata={
        "chunk_id": f"DOC-001#{index}", "document_id": "DOC-001", "title": "示例",
        "section": str(index), "source": "data/DOC-001.md", "category": "data",
    })


def test_repeated_upsert_keeps_ids_and_updates_content(settings):
    rows = {}

    def upsert(*, collection_name, data):
        assert collection_name == settings.COLLECTION
        rows.update({row["chunk_id"]: row for row in data})
        return {"upsert_count": len(data)}

    client = Mock()
    client.upsert.side_effect = upsert
    chunks = [chunk(index) for index in range(103)]
    vectors = [[float(index + 1), 1.0] for index in range(103)]
    assert milvus.upsert_chunks(client, chunks, vectors) == 103
    assert [len(call.kwargs["data"]) for call in client.upsert.call_args_list] == [100, 3]
    assert milvus.upsert_chunks(client, [chunk(0, "修订条款")], [[0.1, 0.2]]) == 1
    assert len(rows) == 103
    assert rows["DOC-001#0"]["content"] == "修订条款"
    assert rows["DOC-001#0"]["embedding_model"] == "offline-test"
    assert rows["DOC-001#0"]["source"] == "data/DOC-001.md"
    assert "chunk_id" in rows["DOC-001#0"]


@pytest.mark.parametrize("vectors", [
    [], [[1.0]], [[0.0, 0.0]], [[float("nan"), 1.0]], [[float("inf"), 1.0]],
])
def test_invalid_vectors_never_write(settings, vectors):
    client = Mock()
    with pytest.raises(ValueError):
        milvus.upsert_chunks(client, [chunk()], vectors)
    client.upsert.assert_not_called()


def test_all_rows_validated_before_first_batch(settings):
    client = Mock()
    chunks = [chunk(index) for index in range(101)]
    vectors = [[1.0, 0.0] for _ in chunks]
    vectors[-1] = [1.0]
    with pytest.raises(ValueError):
        milvus.upsert_chunks(client, chunks, vectors)
    client.upsert.assert_not_called()


def test_duplicate_ids_and_missing_sources_never_write(settings):
    client = Mock()
    with pytest.raises(ValueError, match="ID 重复"):
        milvus.upsert_chunks(client, [chunk(), chunk()], [[1.0, 0.0], [1.0, 0.0]])
    document = chunk()
    del document.metadata["source"]
    with pytest.raises(ValueError, match="来源信息"):
        milvus.upsert_chunks(client, [document], [[1.0, 0.0]])
    client.upsert.assert_not_called()


def test_partial_write_acknowledgement_is_not_success(settings):
    client = Mock()
    client.upsert.return_value = {"upsert_count": 0}
    with pytest.raises(RuntimeError, match="未确认"):
        milvus.upsert_chunks(client, [chunk()], [[1.0, 0.0]])
    client.flush.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "embedding", "verification"])
async def test_pipeline_verifies_rows_and_always_closes(settings, tmp_path, monkeypatch, failure):
    (tmp_path / "DOC-001.md").write_text("# 示例\n\n## 1.1 条款\n\n正文。", encoding="utf-8")
    client = Mock()
    client.upsert.return_value = {"upsert_count": 1}
    client.query.return_value = [{"count(*)": 0 if failure == "verification" else 1}]
    monkeypatch.setattr(milvus, "init_milvus", lambda: client)
    embed = AsyncMock(return_value=[[1.0, 0.0]])
    if failure == "embedding":
        embed.side_effect = RuntimeError("embedding failed")
    monkeypatch.setattr(embedding, "embed_texts", embed)
    if failure:
        with pytest.raises(RuntimeError):
            await resource2chunks.ingest_documents((tmp_path,))
        if failure == "embedding":
            client.upsert.assert_not_called()
    else:
        result = await resource2chunks.ingest_documents((tmp_path,))
        assert result == {"documents": 1, "chunks": 1, "upserted": 1, "verified": 1}
        assert client.query.call_args.kwargs["consistency_level"] == "Strong"
        assert "DOC-001#1.1" in client.query.call_args.kwargs["filter"]
    client.close.assert_called_once()
