"""把文本变成向量。

全项目只有这里调向量模型：灌库（政策条款）和检索（用户问题）都必须走它，
否则两边用的模型或维度不一致，算出来的相似度没有任何意义。
"""

from functools import cache

from langchain_core.embeddings import Embeddings

# text-embedding-v4 单次最多 10 条，超过会被接口直接拒掉。
BATCH_SIZE = 10


@cache
def _get_embedding_model() -> Embeddings:
    """首次使用时创建并复用向量客户端，不连带初始化聊天模型。"""
    from langchain.embeddings import init_embeddings

    from supportflow.core.config import settings

    return init_embeddings(
        model=settings.EMBEDDING_MODEL,
        provider="openai",
        api_key=settings.DASHSCOPE_API_KEY.get_secret_value(),
        base_url=settings.DASHSCOPE_BASE_URL,
        dimensions=settings.EMBEDDING_DIM,
        chunk_size=BATCH_SIZE,
        check_embedding_ctx_length=False,
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量，返回顺序与入参一一对应。"""
    if not texts:
        return []

    if any(not text.strip() for text in texts):
        raise ValueError("待向量化的文本不能为空或纯空白")
    # LangChain 按模型的 chunk_size 自动分批，无需再写一层循环。
    return await _get_embedding_model().aembed_documents(texts)


async def embed_query(text: str) -> list[float]:
    """把一句查询转成向量，与文档共用模型和维度配置。"""
    if not text.strip():
        raise ValueError("查询文本不能为空或纯空白")
    return await _get_embedding_model().aembed_query(text)
