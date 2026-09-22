"""倒数排名融合：只使用各路的名次，不比较 BM25 与 COSINE 原始分数。"""

from supportflow.retrieval.types import RetrievedChunk

DEFAULT_RRF_K = 60
DEFAULT_TOP_K = 5


def validate_rrf_options(top_k: int, rrf_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
        raise ValueError("top_k 必须是 1 到 100 之间的整数")
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int) or rrf_k < 1:
        raise ValueError("rrf_k 必须是正整数")


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    *,
    top_k: int = DEFAULT_TOP_K,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """各路先按 chunk_id 去重，再从 1 计名次，累加 1 / (rrf_k + rank)。

    输入列表必须已经按各自相关性排好序。同 ID 保留首次出现的正文和来源，
    因而调用方应使用同版本的语料。返回的 score 是 RRF 分数，输入不会被修改。
    """
    validate_rrf_options(top_k, rrf_k)
    chunks: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        seen: set[str] = set()
        for chunk in ranked:
            chunk_id = chunk["chunk_id"]
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank = len(seen)
            if chunk_id not in chunks:
                chunks[chunk_id] = chunk
                scores[chunk_id] = 0.0
            scores[chunk_id] += 1.0 / (rrf_k + rank)

    # 分数相同按 ID 排序，避免并发完成顺序影响最终结果。
    ordered_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [{**chunks[chunk_id], "score": scores[chunk_id]} for chunk_id in ordered_ids[:top_k]]
