"""并发执行向量与 BM25 召回，经 RRF 融合后按需重排，生成本轮证据列表。"""

import argparse
import asyncio
import json
import logging
import math
from collections.abc import Awaitable
from typing import Literal

from supportflow.retrieval.retrieving.bm25 import retrieve_bm25
from supportflow.retrieval.retrieving.rerank import rerank_chunks
from supportflow.retrieval.retrieving.rrf import (
    DEFAULT_RRF_K, DEFAULT_TOP_K, reciprocal_rank_fusion, validate_rrf_options,
)
from supportflow.retrieval.retrieving.vector import DEFAULT_MIN_SCORE, retrieve as retrieve_vector
from supportflow.retrieval.types import RetrievalUnavailable, RetrievedChunk

DEFAULT_CANDIDATE_K = 20
logger = logging.getLogger(__name__)


async def _recall(
    call: Awaitable[list[RetrievedChunk]],
) -> list[RetrievedChunk] | RetrievalUnavailable:
    # 仅把已知检索故障交给降级逻辑；取消和代码错误仍向调用方传播。
    try:
        return await call
    except RetrievalUnavailable as exc:
        return exc


async def retrieve_hybrid(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    rrf_k: int = DEFAULT_RRF_K,
    min_score: float = DEFAULT_MIN_SCORE,
    rerank: bool = False,
    category: Literal["data", "policies"] | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """每路最多 candidate_k 条，融合后最多返回 top_k 条；min_score 只用于向量路。

    rerank=True 时融合结果先保留 candidate_k 条再重排，让重排从更大的候选池里
    挑出 top_k 条；重排不可用时退回融合顺序，不影响本轮能否拿到证据。

    单路失败但另一路有候选时继续返回结果并记录降级日志；有故障且没有任何
    可用候选时抛 RetrievalUnavailable。只有两路正常无匹配才返回 []。
    """
    query = query.strip()
    if not query:
        raise ValueError("检索问题不能为空")
    validate_rrf_options(top_k, rrf_k)
    if (
        isinstance(candidate_k, bool) or not isinstance(candidate_k, int)
        or not top_k <= candidate_k <= 100
    ):
        raise ValueError("candidate_k 必须是 top_k 到 100 之间的整数")
    if not math.isfinite(min_score) or not -1 <= min_score <= 1:
        raise ValueError("min_score 必须在 -1 到 1 之间")
    if category not in (None, "data", "policies"):
        raise ValueError("category 只能是 data 或 policies")
    if document_ids is not None:
        if any(not isinstance(value, str) or not value.strip() for value in document_ids):
            raise ValueError("document_ids 不能包含空文档 ID")
        if not document_ids:
            return []

    results = await asyncio.gather(
        _recall(retrieve_vector(
            query, top_k=candidate_k, min_score=min_score,
            category=category, document_ids=document_ids,
        )),
        _recall(retrieve_bm25(
            query, top_k=candidate_k, category=category, document_ids=document_ids,
        )),
    )
    ranked_lists: list[list[RetrievedChunk]] = []
    failed_sources: list[str] = []
    for source, result in zip(("vector", "bm25"), results):
        if isinstance(result, RetrievalUnavailable):
            failed_sources.append(source)
            # 不记录异常正文，避免第三方连接参数或请求内容进入日志。
            logger.warning("混合检索 %s 召回不可用", source)
        else:
            ranked_lists.append(result)

    # 融合先保留 candidate_k 条，重排才有挑选余地；最终一律截到 top_k 条。
    fused = reciprocal_rank_fusion(ranked_lists, top_k=candidate_k, rrf_k=rrf_k)
    if not fused and failed_sources:
        raise RetrievalUnavailable(f"混合检索暂不可用（{', '.join(failed_sources)} 召回失败）")

    if not rerank:
        return fused[:top_k]
    try:
        return await rerank_chunks(query, fused, top_n=top_k)
    except RetrievalUnavailable:
        # 重排坏了也要照常给证据，退回融合顺序。
        logger.warning("混合检索重排不可用，退回融合顺序")
        return fused[:top_k]



