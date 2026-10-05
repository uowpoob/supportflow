"""本地 BM25 召回：复用向量入库的文档切分，不依赖模型或 Milvus。

首次查询惰性构建内存索引；修改资料后重启进程或 clear_index_cache()。
这里只返回 BM25 候选，不合并向量结果，也不实现 RRF。
"""

import argparse
import asyncio
import json
import math
import re
import unicodedata
from functools import lru_cache
from typing import Literal

import jieba
from rank_bm25 import BM25Okapi

from supportflow.retrieval.resource2chunks import load_documents, split_documents
from supportflow.retrieval.types import TEXT_FIELDS, RetrievalUnavailable, RetrievedChunk

DEFAULT_TOP_K = 5
# 连字符型号整体保留，避免 WH-1000XM5 / USB-C 被拆成无关碎片。
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*|[^\W\d_a-z]+", re.UNICODE)
_tokenizer = jieba.Tokenizer()


def tokenize(text: str) -> list[str]:
    """文档与问题使用同一规则：全半角归一、英文小写、中文搜索分词。"""
    text = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in TOKEN_PATTERN.finditer(text):
        term = match.group()
        if term.isascii():
            tokens.append(term)
        else:
            tokens.extend(word for word in _tokenizer.cut_for_search(term) if word.strip())
    return tokens


class BM25Index:
    """固定语料的内存索引；过滤发生在 Top-K 截取之前。"""

    def __init__(self) -> None:
        chunks = split_documents(load_documents())
        self.chunks = tuple({
            **chunk.metadata, "content": chunk.page_content,
        } for chunk in chunks)
        corpus = [tokenize(chunk["content"]) for chunk in self.chunks]
        if not corpus or not any(corpus):
            raise ValueError("没有可建立 BM25 索引的正文片段")
        self.model = BM25Okapi(corpus, k1=1.5, b=0.75)

    def search(
        self,
        tokens: list[str],
        *,
        top_k: int,
        category: str | None,
        document_ids: list[str] | None,
    ) -> list[RetrievedChunk]:
        allowed_ids = set(document_ids) if document_ids is not None else None
        query_terms = set(tokens)
        # 无词项交集时不能用 get_top_n 返回任意零分片段。
        # Okapi 在很小的语料中可能为匹配词打零分/负分，不能靠 score > 0 判断匹配。
        indices = [i for i, chunk in enumerate(self.chunks)
                   if (category is None or chunk["category"] == category)
                   and (allowed_ids is None or chunk["document_id"] in allowed_ids)
                   and not query_terms.isdisjoint(self.model.doc_freqs[i])]
        if not indices:
            return []
        scores = self.model.get_batch_scores(tokens, indices)
        if not all(math.isfinite(score) for score in scores):
            raise ValueError("BM25 分数无效")
        ranked = sorted(zip(indices, scores), key=lambda item: (-item[1], self.chunks[item[0]]["chunk_id"]))
        return [{**{key: self.chunks[i][key] for key in TEXT_FIELDS}, "score": float(score)}
                for i, score in ranked[:top_k]]


@lru_cache(maxsize=1)
def _get_index() -> BM25Index:
    return BM25Index()


def clear_index_cache() -> None:
    """清除当前进程缓存，下一次查询重新读取资料；在无在途检索时调用。"""
    _get_index.cache_clear()


def _search(
    query: str, *, top_k: int, category: str | None, document_ids: list[str] | None,
) -> list[RetrievedChunk]:
    tokens = tokenize(query)
    if not tokens:
        return []
    return _get_index().search(tokens, top_k=top_k, category=category, document_ids=document_ids)


async def retrieve_bm25(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    category: Literal["data", "policies"] | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """按 BM25 原始分数降序召回；无词项匹配返回 []，索引失败抛异常。"""
    query = query.strip()
    if not query:
        raise ValueError("检索问题不能为空")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
        raise ValueError("top_k 必须是 1 到 100 之间的整数")
    if category not in (None, "data", "policies"):
        raise ValueError("category 只能是 data 或 policies")
    if document_ids is not None:
        if any(not isinstance(value, str) or not value.strip() for value in document_ids):
            raise ValueError("document_ids 不能包含空文档 ID")
        if not document_ids:
            return []
    try:
        return await asyncio.to_thread(
            _search, query, top_k=top_k, category=category, document_ids=document_ids,
        )
    except Exception as exc:
        raise RetrievalUnavailable(f"BM25 检索暂不可用（{type(exc).__name__}）") from exc


d
