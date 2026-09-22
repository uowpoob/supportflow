"""不同召回方式共用的片段结构；score 的含义由召回方式决定。"""

from typing import TypedDict

TEXT_FIELDS = ("document_id", "chunk_id", "title", "section", "source", "category", "content")


class RetrievedChunk(TypedDict):
    document_id: str
    chunk_id: str
    title: str
    section: str
    source: str
    category: str
    content: str
    score: float


class RetrievalUnavailable(RuntimeError):
    """索引、配置或检索服务失败，与正常查询但没有匹配区分。"""
