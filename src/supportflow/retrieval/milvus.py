"""Milvus 集合初始化与片段写入；导入模块不会连接或修改数据库。"""
import math

from langchain_core.documents import Document
from pymilvus import DataType, MilvusClient

WRITE_BATCH_SIZE = 100
CHUNK_ID_MAX_LENGTH = 512


def init_milvus() -> MilvusClient:
    """缺少库或集合时才创建；已有向量维度不匹配则报错，绝不删集合。

    返回的客户端由调用方使用，并在结束时调用 close() 关闭。
    """
    from supportflow.core.config import settings

    if not settings.MILVUS_URI.strip():
        raise ValueError("请先配置 MILVUS_URI")

    client = MilvusClient(uri=settings.MILVUS_URI, timeout=30)
    try:
        if settings.DB_NAME not in client.list_databases():
            client.create_database(db_name=settings.DB_NAME)
        client.use_database(db_name=settings.DB_NAME)

        if not client.has_collection(collection_name=settings.COLLECTION):
            client.create_collection(
                collection_name=settings.COLLECTION,
                dimension=settings.EMBEDDING_DIM,
                metric_type="COSINE",
                primary_field_name="chunk_id",
                id_type="string",
                max_length=CHUNK_ID_MAX_LENGTH,
                auto_id=False,
                enable_dynamic_field=True,
                consistency_level="Strong",
            )
        else:
            schema = client.describe_collection(collection_name=settings.COLLECTION)
            vector = next(
                (field for field in schema["fields"] if field["name"] == "vector"),
                None,
            )
            if (
                vector is None
                or vector["type"] != DataType.FLOAT_VECTOR
                or int(vector.get("params", {}).get("dim", 0)) != settings.EMBEDDING_DIM
            ):
                raise ValueError(
                    f"集合 {settings.COLLECTION} 的 vector 字段必须是 "
                    f"{settings.EMBEDDING_DIM} 维 FLOAT_VECTOR；"
                    "已有集合已保留，请检查配置或使用新的集合名"
                )
            primary = next(
                (field for field in schema["fields"] if field.get("is_primary")), None,
            )
            if (
                primary is None
                or primary["name"] != "chunk_id"
                or primary["type"] != DataType.VARCHAR
                or int(primary.get("params", {}).get("max_length", 0)) < CHUNK_ID_MAX_LENGTH
                or schema.get("auto_id", False)
                or primary.get("auto_id", False)
                or not schema.get("enable_dynamic_field", False)
            ):
                raise ValueError(
                    "集合需要 chunk_id 字符串主键（max_length >= 512）、"
                    "auto_id=False 和动态字段；已有集合已保留，请使用新的集合名"
                )
    except Exception:
        client.close()
        raise

    return client


def prepare_rows(
    chunks: list[Document],
    vectors: list[list[float]],
) -> list[dict]:
    """校验全部片段和向量；纯本地操作，可在清库前调用。"""
    from supportflow.core.config import settings

    if len(chunks) != len(vectors):
        raise ValueError("片段数量与向量数量不一致，取消写入")
    if not chunks:
        return []

    rows = []
    ids: set[str] = set()
    metadata_fields = ("chunk_id", "document_id", "title", "section", "source", "category")
    for chunk, vector in zip(chunks, vectors, strict=True):
        metadata = chunk.metadata
        if any(not isinstance(metadata.get(key), str) or not metadata[key].strip() for key in metadata_fields):
            raise ValueError("片段缺少有效的 ID、标题或来源信息，取消写入")
        chunk_id = metadata["chunk_id"]
        if chunk_id in ids or len(chunk_id.encode("utf-8")) > CHUNK_ID_MAX_LENGTH:
            raise ValueError(f"片段 ID 重复或过长：{chunk_id}")
        ids.add(chunk_id)
        if not chunk.page_content.strip():
            raise ValueError(f"片段正文为空：{chunk_id}")
        if (
            len(vector) != settings.EMBEDDING_DIM
            or not all(math.isfinite(value) for value in vector)
            or not any(value != 0 for value in vector)
        ):
            raise ValueError(f"向量维度错误、包含非有限值或为零向量：{chunk_id}")
        rows.append({
            **{key: metadata[key] for key in metadata_fields},
            "content": chunk.page_content,
            "vector": vector,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dim": settings.EMBEDDING_DIM,
        })

    return rows


def clear_chunks(client: MilvusClient) -> int:
    """删除配置知识集合的所有记录，保留集合、索引及其他数据库。"""
    from supportflow.core.config import settings

    query = dict(collection_name=settings.COLLECTION, filter="",
                 output_fields=["count(*)"], consistency_level="Strong")
    before = client.query(**query)[0]["count(*)"]
    if before:
        client.delete(collection_name=settings.COLLECTION, filter='chunk_id >= ""')
        client.flush(collection_name=settings.COLLECTION)
    remaining = client.query(**query)[0]["count(*)"]
    if remaining:
        raise RuntimeError(f"清库校验失败：仍有 {remaining} 条记录")
    return before


def upsert_chunks(client: MilvusClient, chunks: list[Document], vectors: list[list[float]]) -> int:
    """全部校验后分批写入，以 chunk_id 更新或新增；批次间不具备事务原子性。"""
    from supportflow.core.config import settings

    rows = prepare_rows(chunks, vectors)
    if not rows:
        return 0
    written = 0
    for start in range(0, len(rows), WRITE_BATCH_SIZE):
        batch = rows[start:start + WRITE_BATCH_SIZE]
        result = client.upsert(collection_name=settings.COLLECTION, data=batch)
        if result.get("upsert_count") != len(batch):
            raise RuntimeError(f"Milvus 未确认本批全部写入，已确认前 {written} 条；可重新运行")
        written += len(batch)
    client.flush(collection_name=settings.COLLECTION)
    return written
