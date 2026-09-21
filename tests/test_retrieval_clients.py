"""用真实 SDK 的分批逻辑和模拟传输验证配置，不访问网络或数据库。"""

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import SecretStr
from pymilvus import DataType

from supportflow.retrieval import embedding, milvus


@pytest.fixture
def settings(monkeypatch):
    config = SimpleNamespace(
        EMBEDDING_MODEL="text-embedding-v4",
        EMBEDDING_DIM=512,
        DASHSCOPE_API_KEY=SecretStr("offline-test-key"),
        DASHSCOPE_BASE_URL="https://example.invalid/v1",
        MILVUS_URI="http://example.invalid:19530",
        DB_NAME="knowledge_test",
        COLLECTION="documents_test",
    )
    monkeypatch.setitem(sys.modules, "supportflow.core.config", SimpleNamespace(settings=config))
    embedding._get_embedding_model.cache_clear()
    yield config
    embedding._get_embedding_model.cache_clear()


@pytest.mark.asyncio
async def test_embedding_batches_and_query_share_config(settings):
    model = embedding._get_embedding_model()
    assert model is embedding._get_embedding_model()

    async def create(**kwargs):
        assert kwargs["dimensions"] == 512
        assert kwargs["model"] == "text-embedding-v4"
        return {"data": [{"embedding": [float(text)] * 512} for text in kwargs["input"]]}

    model.async_client = SimpleNamespace(create=AsyncMock(side_effect=create))
    vectors = await embedding.embed_texts([str(index) for index in range(23)])
    assert [len(call.kwargs["input"]) for call in model.async_client.create.call_args_list] == [10, 10, 3]
    assert [vector[0] for vector in vectors] == list(range(23))
    assert all(len(vector) == 512 for vector in vectors)
    assert await embedding.embed_query("24") == [24.0] * 512


@pytest.mark.asyncio
async def test_empty_inputs_do_not_create_client(monkeypatch):
    factory = Mock(side_effect=AssertionError("不应创建客户端"))
    monkeypatch.setattr(embedding, "_get_embedding_model", factory)
    assert await embedding.embed_texts([]) == []
    with pytest.raises(ValueError):
        await embedding.embed_texts(["有效文本", "  "])
    with pytest.raises(ValueError):
        await embedding.embed_query("\n ")
    factory.assert_not_called()


@pytest.fixture
def client(monkeypatch, settings):
    client = Mock()
    client.list_databases.return_value = [settings.DB_NAME]
    client.has_collection.return_value = True
    client.describe_collection.return_value = {"auto_id": False, "enable_dynamic_field": True, "fields": [
        {"name": "chunk_id", "type": DataType.VARCHAR, "is_primary": True, "params": {"max_length": 512}},
        {"name": "vector", "type": DataType.FLOAT_VECTOR, "params": {"dim": 512}},
    ]}
    monkeypatch.setattr(milvus, "MilvusClient", Mock(return_value=client))
    return client


def test_milvus_reuses_existing_collection(client):
    assert milvus.init_milvus() is client
    client.create_database.assert_not_called()
    client.create_collection.assert_not_called()
    client.drop_collection.assert_not_called()
    client.close.assert_not_called()


def test_milvus_creates_only_missing_resources(client, settings):
    client.list_databases.return_value = []
    client.has_collection.return_value = False
    milvus.init_milvus()
    client.create_database.assert_called_once_with(db_name=settings.DB_NAME)
    client.use_database.assert_called_once_with(db_name=settings.DB_NAME)
    client.create_collection.assert_called_once_with(
        collection_name=settings.COLLECTION, dimension=512, metric_type="COSINE",
        primary_field_name="chunk_id", id_type="string", max_length=512,
        auto_id=False, enable_dynamic_field=True, consistency_level="Strong",
    )
    client.drop_collection.assert_not_called()


@pytest.mark.parametrize("fields", [
    [],
    [{"name": "vector", "type": DataType.FLOAT_VECTOR, "params": {"dim": 1024}}],
    [{"name": "vector", "type": DataType.BINARY_VECTOR, "params": {"dim": 512}}],
])
def test_incompatible_collection_is_preserved(client, fields):
    client.describe_collection.return_value = {"fields": fields}
    with pytest.raises(ValueError, match="已有集合已保留"):
        milvus.init_milvus()
    client.drop_collection.assert_not_called()
    client.create_collection.assert_not_called()
    client.close.assert_called_once()


def test_milvus_failure_closes_client(client):
    client.list_databases.side_effect = RuntimeError("服务不可用")
    with pytest.raises(RuntimeError, match="服务不可用"):
        milvus.init_milvus()
    client.close.assert_called_once()


def test_old_integer_primary_key_is_preserved(client):
    client.describe_collection.return_value["fields"][0] = {
        "name": "id", "type": DataType.INT64, "is_primary": True,
    }
    with pytest.raises(ValueError, match="chunk_id 字符串主键"):
        milvus.init_milvus()
    client.drop_collection.assert_not_called()
    client.create_collection.assert_not_called()
    client.close.assert_called_once()


def test_missing_uri_does_not_connect(client, settings):
    settings.MILVUS_URI = " "
    with pytest.raises(ValueError, match="MILVUS_URI"):
        milvus.init_milvus()
    milvus.MilvusClient.assert_not_called()


def test_import_does_not_initialize_clients(monkeypatch):
    import langchain.embeddings
    import pymilvus

    vector_factory = Mock(side_effect=AssertionError("导入不应连接数据库"))
    model_factory = Mock(side_effect=AssertionError("导入不应初始化模型"))
    # context 内 reload 捕获副作用，结束后恢复真实类绑定。
    with monkeypatch.context() as patch:
        patch.setattr(pymilvus, "MilvusClient", vector_factory)
        patch.setattr(langchain.embeddings, "init_embeddings", model_factory)
        importlib.reload(milvus)
        importlib.reload(embedding)
        vector_factory.assert_not_called()
        model_factory.assert_not_called()
    importlib.reload(milvus)
