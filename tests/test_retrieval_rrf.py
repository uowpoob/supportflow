"""RRF 纯函数测试：名次贡献、跨路融合、去重及确定性。"""

from copy import deepcopy

import pytest

from supportflow.retrieval.retrieving.rrf import reciprocal_rank_fusion


def chunk(chunk_id: str, score: float = 0.8):
    return {
        "document_id": "manual", "chunk_id": chunk_id, "title": "使用指南",
        "section": "连接", "source": "data/manual.md", "category": "data",
        "content": f"片段 {chunk_id} 的正文", "score": score,
    }


def test_fusion_uses_one_based_ranks_and_promotes_shared_candidate():
    lists = [[chunk("a"), chunk("shared")], [chunk("b", 100), chunk("shared", 5)]]
    before = deepcopy(lists)
    result = reciprocal_rank_fusion(lists)
    assert [item["chunk_id"] for item in result] == ["shared", "a", "b"]
    assert result[0]["score"] == pytest.approx(2 / 62)
    assert result[1]["score"] == pytest.approx(1 / 61)
    assert result[0]["content"] == lists[0][1]["content"]
    assert result[0]["source"] == "data/manual.md"
    assert lists == before
    result[0]["content"] = "调用方修改"
    assert lists == before


def test_raw_scores_do_not_affect_fusion():
    lists = [[chunk("a", 0.99), chunk("b", 0.5)], [chunk("b", 999), chunk("a", -1)]]
    expected = reciprocal_rank_fusion(lists)
    for ranked in lists:
        for item in ranked:
            item["score"] *= -1000
    assert reciprocal_rank_fusion(lists) == expected


def test_each_route_deduplicates_before_assigning_ranks():
    result = reciprocal_rank_fusion([[chunk("a"), chunk("a"), chunk("b")], [chunk("b")]])
    assert [item["chunk_id"] for item in result] == ["b", "a"]
    assert result[0]["score"] == pytest.approx(1 / 62 + 1 / 61)
    assert result[1]["score"] == pytest.approx(1 / 61)


def test_same_document_different_chunks_remain_separate():
    assert len(reciprocal_rank_fusion([[chunk("manual#1"), chunk("manual#2")]])) == 2


def test_ties_use_chunk_id_and_first_payload_wins():
    first = chunk("a")
    other = {**first, "content": "另一个版本"}
    result = reciprocal_rank_fusion([[chunk("b"), first], [other, chunk("b")]])
    assert [item["chunk_id"] for item in result] == ["a", "b"]
    assert result[0]["content"] == first["content"]


def test_top_k_is_applied_after_fusion_and_rrf_constant_is_configurable():
    result = reciprocal_rank_fusion(
        [[chunk("a"), chunk("shared")], [chunk("b"), chunk("shared")]], top_k=1, rrf_k=1,
    )
    assert len(result) == 1
    assert result[0]["chunk_id"] == "shared"
    assert result[0]["score"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("lists", [[], [[]], [[], []]])
def test_empty_inputs(lists):
    assert reciprocal_rank_fusion(lists) == []


@pytest.mark.parametrize("kwargs", [
    {"top_k": 0}, {"top_k": 101}, {"top_k": True}, {"top_k": 1.5},
    {"rrf_k": 0}, {"rrf_k": -1}, {"rrf_k": True}, {"rrf_k": 1.5},
])
def test_invalid_options(kwargs):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([], **kwargs)
