"""独立向量召回：问题向量化 → Milvus COSINE 检索 → 返回带来源的候选片段。

这里只召回，不生成回答，不写数据库。score 是相似度，不是答案正确率。
"""

import argparse
import asyncio
import json
import math
from typing import Literal

from pymilvus import DataType, MilvusClient

from supportflow.retrieval.embedding import embed_query
from supportflow.retrieval.types import TEXT_FIELDS, RetrievalUnavailable, RetrievedChunk

DEFAULT_TOP_K = 5
# 起始门槛，需用后续标注数据校准；不代表已经验证的相关性判定标准。
DEFAULT_MIN_SCORE = 0.5
MILVUS_TIMEOUT = 10
EMBEDDING_TIMEOUT = 30


def _search_milvus(
    vector: list[float],
    *,
    top_k: int,
    min_score: float,
    category: str | None,
    document_ids: list[str] | None,
) -> list[RetrievedChunk]:
    from supportflow.core.config import settings

    if not settings.MILVUS_URI.strip():
        raise ValueError("未配置 MILVUS_URI")
    if (
        len(vector) != settings.EMBEDDING_DIM
        or not all(math.isfinite(value) for value in vector)
        or not any(value != 0 for value in vector)
    ):
        raise ValueError("查询向量的维度或数值无效")

    # 指定已有数据库；不能调用会自动建库的 init_milvus()。
    client = MilvusClient(uri=settings.MILVUS_URI, db_name=settings.DB_NAME, timeout=MILVUS_TIMEOUT)
    try:
        if not client.has_collection(collection_name=settings.COLLECTION, timeout=MILVUS_TIMEOUT):
            raise ValueError("知识集合不存在，请先入库")
        schema = client.describe_collection(collection_name=settings.COLLECTION, timeout=MILVUS_TIMEOUT)
        field = next((field for field in schema["fields"] if field["name"] == "vector"), None)
        if (
            field is None
            or field["type"] != DataType.FLOAT_VECTOR
            or int(field.get("params", {}).get("dim", 0)) != settings.EMBEDDING_DIM
        ):
            raise ValueError("知识集合向量字段与当前模型维度不匹配")

        # 数值相同的向量维度不保证属于同一模型，按入库记录的模型一起过滤。
        filters = [
            f"embedding_model == {json.dumps(settings.EMBEDDING_MODEL, ensure_ascii=False)}",
            f"embedding_dim == {settings.EMBEDDING_DIM}",
        ]
        if category is not None:
            filters.append(f"category == {json.dumps(category)}")
        if document_ids is not None:
            filters.append(f"document_id in {json.dumps(document_ids, ensure_ascii=False)}")

        client.load_collection(collection_name=settings.COLLECTION, timeout=MILVUS_TIMEOUT)
        results = client.search(
            collection_name=settings.COLLECTION,
            data=[vector],
            anns_field="vector",
            search_params={"metric_type": "COSINE", "params": {}},
            filter=" and ".join(filters),
            limit=top_k,
            output_fields=list(TEXT_FIELDS),
            consistency_level="Strong",
            timeout=MILVUS_TIMEOUT,
        )
        chunks: list[RetrievedChunk] = []
        seen: set[str] = set()
        # COSINE 越大越相似。这里再过滤低分，结果可以少于 top_k，甚至为空。
        for hit in sorted(results[0] if results else [], key=lambda item: item["distance"], reverse=True):
            score = float(hit["distance"])
            if not math.isfinite(score) or score < min_score:
                continue
            entity = hit["entity"]
            if any(not isinstance(entity.get(key), str) or not entity[key].strip() for key in TEXT_FIELDS):
                raise ValueError("召回片段缺少正文或来源，请检查入库数据")
            if entity["chunk_id"] in seen:
                continue
            seen.add(entity["chunk_id"])
            chunks.append({**{key: entity[key] for key in TEXT_FIELDS}, "score": score})
        return chunks
    finally:
        client.close()


async def retrieve(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    category: Literal["data", "policies"] | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """召回最多 top_k 条；正常无匹配返回 []，外部服务失败抛 RetrievalUnavailable。"""
    query = query.strip()
    if not query:
        raise ValueError("检索问题不能为空")
    if not 1 <= top_k <= 100:
        raise ValueError("top_k 必须在 1 到 100 之间")
    if not math.isfinite(min_score) or not -1 <= min_score <= 1:
        raise ValueError("min_score 必须在 -1 到 1 之间")
    if category not in (None, "data", "policies"):
        raise ValueError("category 只能是 data 或 policies")
    if document_ids is not None:
        if any(not isinstance(value, str) or not value.strip() for value in document_ids):
            raise ValueError("document_ids 不能包含空文档 ID")
        if not document_ids:
            return []

    try:
        vector = await asyncio.wait_for(embed_query(query), timeout=EMBEDDING_TIMEOUT)
        return await asyncio.to_thread(
            _search_milvus, vector,
            top_k=top_k, min_score=min_score, category=category, document_ids=document_ids,
        )
    except Exception as exc:
        # 不向终端或对话输出 SDK 异常中的连接信息、密钥或请求正文。
        raise RetrievalUnavailable(f"知识检索暂不可用（{type(exc).__name__}）") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="从已有 Milvus 知识库召回相关片段，不生成回答")
    parser.add_argument("query", help="要检索的问题")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--category", choices=["data", "policies"])
    parser.add_argument("--document-id", action="append", dest="document_ids", help="限定文档，可重复传入")
    args = parser.parse_args()
    try:
        chunks = asyncio.run(retrieve(
            args.query, top_k=args.top_k, min_score=args.min_score,
            category=args.category, document_ids=args.document_ids,
        ))
    except (ValueError, RetrievalUnavailable) as exc:
        parser.exit(status=1, message=f"{exc}\n")
    print(json.dumps({"query": args.query, "count": len(chunks), "chunks": chunks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
