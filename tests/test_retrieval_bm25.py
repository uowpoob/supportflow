"""BM25 离线测试：真实分词/打分、来源对齐、过滤和缓存生命周期。"""

from unittest.mock import Mock

import pytest

from supportflow.retrieval.retrieving import bm25
from supportflow.retrieval.resource2chunks import load_documents, split_documents
from supportflow.retrieval.types import RetrievalUnavailable


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    data = tmp_path / "data"
    policies = tmp_path / "policies"
    data.mkdir()
    policies.mkdir()
    (data / "sony.md").write_text(
        "# 索尼 WH-1000XM5\n\n## 1 有线模式\n\n没电后可以连接音频线聆听音乐。", encoding="utf-8",
    )
    (data / "charger.md").write_text(
        "# Anker A2666\n\n## 1 充电\n\nUSB-C 接口支持快速充电。", encoding="utf-8",
    )
    (policies / "returns.md").write_text(
        "# 退货政策\n\n## 1 运费\n\n无理由退货运费由消费者承担。", encoding="utf-8",
    )
    loader = Mock(side_effect=lambda: load_documents((data, policies)))
    monkeypatch.setattr(bm25, "load_documents", loader)
    bm25.clear_index_cache()
    yield data, policies, loader
    bm25.clear_index_cache()


def test_tokenizer_normalizes_chinese_models_and_punctuation():
    tokens = bm25.tokenize("索尼ＷＨ-１０００ＸＭ５，USB-C接口，七天无理由退货！")
    assert "wh-1000xm5" in tokens
    assert "usb-c" in tokens
    assert "退货" in tokens
    assert not any(token in tokens for token in ["，", "！", "-", " "])
    assert bm25.tokenize("USB-C") == bm25.tokenize("ｕｓｂ-ｃ")


@pytest.mark.asyncio
async def test_exact_model_retrieval_preserves_shared_chunk_identity(corpus):
    data, policies, _ = corpus
    results = await bm25.retrieve_bm25("wh-1000xm5", top_k=1)
    original = split_documents(load_documents((data, policies)))[1]
    assert len(results) == 1
    assert results[0]["chunk_id"] == "data/sony.md#1"
    assert results[0]["content"] == original.page_content
    assert results[0]["source"] == "data/sony.md"
    assert results[0]["score"] > 0
    assert results[0].keys() == {*bm25.TEXT_FIELDS, "score"}


@pytest.mark.asyncio
async def test_ranked_results_filters_and_top_k(corpus):
    results = await bm25.retrieve_bm25("WH-1000XM5 退货", top_k=2)
    assert {result["chunk_id"] for result in results} == {"data/sony.md#1", "policies/returns.md#1"}
    assert [result["score"] for result in results] == sorted(
        [result["score"] for result in results], reverse=True,
    )
    assert len(await bm25.retrieve_bm25("WH-1000XM5 退货", top_k=1)) == 1
    filtered = await bm25.retrieve_bm25("WH-1000XM5 退货", top_k=1, category="policies")
    assert [result["chunk_id"] for result in filtered] == ["policies/returns.md#1"]
    filtered = await bm25.retrieve_bm25("WH-1000XM5 退货", document_ids=["data/sony.md"])
    assert [result["chunk_id"] for result in filtered] == ["data/sony.md#1"]
    assert await bm25.retrieve_bm25("退货", category="data", document_ids=["policies/returns.md"]) == []
    assert await bm25.retrieve_bm25("退货", document_ids=["missing"]) == []


@pytest.mark.asyncio
async def test_no_overlap_and_punctuation_do_not_return_arbitrary_chunks(corpus):
    assert await bm25.retrieve_bm25("qzxv987654") == []
    assert await bm25.retrieve_bm25("？！ ---") == []
    assert await bm25.retrieve_bm25("WH-1000XM5", document_ids=[]) == []


@pytest.mark.asyncio
async def test_single_document_with_negative_okapi_score_still_matches(corpus):
    data, policies, loader = corpus
    loader.side_effect = lambda: load_documents((policies,))
    result = await bm25.retrieve_bm25("退货")
    assert len(result) == 1
    assert result[0]["chunk_id"] == "policies/returns.md#1"
    assert await bm25.retrieve_bm25("WH-1000XM5") == []


@pytest.mark.asyncio
async def test_index_is_cached_and_can_be_reloaded_without_leaking_mutations(corpus):
    data, _, loader = corpus
    results = await bm25.retrieve_bm25("A2666")
    results[0]["content"] = "调用方的修改"
    assert "USB-C" in (await bm25.retrieve_bm25("A2666"))[0]["content"]
    assert loader.call_count == 1
    (data / "charger.md").write_text("# 新充电器\n\n新型号 A9999。", encoding="utf-8")
    bm25.clear_index_cache()
    assert await bm25.retrieve_bm25("A2666") == []
    assert (await bm25.retrieve_bm25("A9999"))[0]["chunk_id"] == "data/charger.md#overview"
    assert loader.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"query": " "}, {"query": "q", "top_k": 0}, {"query": "q", "top_k": 101},
    {"query": "q", "top_k": 1.5}, {"query": "q", "top_k": True},
    {"query": "q", "category": "other"}, {"query": "q", "document_ids": [""]},
])
async def test_invalid_arguments_do_not_build_index(corpus, kwargs):
    with pytest.raises(ValueError):
        await bm25.retrieve_bm25(**kwargs)
    corpus[2].assert_not_called()


@pytest.mark.asyncio
async def test_index_failures_are_unavailable_and_retryable(corpus):
    loader = corpus[2]
    loader.side_effect = FileNotFoundError("private filesystem path")
    with pytest.raises(RetrievalUnavailable) as error:
        await bm25.retrieve_bm25("退货")
    assert "private" not in str(error.value)
    loader.side_effect = lambda: load_documents(corpus[:2])
    assert await bm25.retrieve_bm25("退货")


@pytest.mark.asyncio
async def test_empty_chunks_are_unavailable(corpus):
    data = corpus[0]
    (data / "charger.md").write_text("# 空标题", encoding="utf-8")
    corpus[2].side_effect = lambda: load_documents((data,))[:1]
    with pytest.raises(RetrievalUnavailable):
        await bm25.retrieve_bm25("充电")
