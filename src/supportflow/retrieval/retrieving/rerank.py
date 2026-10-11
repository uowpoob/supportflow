"""独立重排：把候选片段交给百炼重排模型，按语义相关性重新排序。

只重排，不召回、不生成回答。这里的 score 是重排分，和向量 COSINE、BM25、
RRF 分都不可比，也不能跨查询比大小，只能在同一批候选内部排序。
"""

import argparse
import asyncio
import json

import httpx

from supportflow.retrieval.types import RetrievalUnavailable, RetrievedChunk

# Qwen3 使用兼容 reranks 协议，GTE 等模型使用百炼原生协议。
RERANK_PATH = "/services/rerank/text-rerank/text-rerank"
RERANK_TIMEOUT = 30
DEFAULT_TOP_N = 5


def _document_text(chunk: RetrievedChunk) -> str:
    """送重排的文本必须与入库时一致。

    content 已经是入库的完整片段（「# 标题」+「## 条款标题」+ 正文，见
    milvus.py 写入的 page_content）。型号常只写在标题里，别只取正文，
    否则重排看不到型号。
    """
    return chunk["content"]


async def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_n: int = DEFAULT_TOP_N,
) -> list[RetrievedChunk]:
    """按接口给出的相关性降序返回最多 top_n 条；接口失败抛 RetrievalUnavailable。"""
    from supportflow.core.config import settings

    query = query.strip()
    if not query:
        raise ValueError("检索问题不能为空")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n 必须是正整数")
    if not chunks:
        return []
    if any(not chunk["content"].strip() for chunk in chunks):
        raise ValueError("待重排的片段缺少正文")

    texts = [_document_text(chunk) for chunk in chunks]
    qwen_compatible = settings.RERANK_MODEL == "qwen3-rerank"
    base_url = settings.DASHSCOPE_NATIVE_BASE_URL.rstrip("/")
    if qwen_compatible:
        url = base_url.removesuffix("/api/v1") + "/compatible-api/v1/reranks"
        payload = {
            "model": settings.RERANK_MODEL, "query": query, "documents": texts,
            "top_n": min(top_n, len(texts)),
        }
    else:
        url = base_url + RERANK_PATH
        payload = {
            "model": settings.RERANK_MODEL,
            "input": {"query": query, "documents": texts},
            "parameters": {"top_n": min(top_n, len(texts))},
        }
    try:
        # trust_env=False：系统代理会截走本机对百炼的请求。
        async with httpx.AsyncClient(trust_env=False, timeout=RERANK_TIMEOUT) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY.get_secret_value()}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            results = data["results"] if qwen_compatible else data["output"]["results"]
    except Exception as exc:
        # 不把 SDK 报错原文（可能带请求正文或连接信息）传给上层。
        raise RetrievalUnavailable(f"重排暂不可用（{type(exc).__name__}）") from exc

    if not isinstance(results, list):
        raise RetrievalUnavailable("重排返回格式异常")
    reranked: list[RetrievedChunk] = []
    for item in results:
        index = item.get("index")
        score = item.get("relevance_score")
        # index 是传进去那份列表的下标，丢了就找不回原片段。
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(chunks):
            raise RetrievalUnavailable("重排返回的片段下标无法对应候选")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RetrievalUnavailable("重排返回的片段分数无效")
        reranked.append({**chunks[index], "score": float(score)})
    return reranked



