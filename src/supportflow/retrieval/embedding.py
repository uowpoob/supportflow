"""把文本变成向量。

全项目只有这里调向量模型：灌库（政策条款）和检索（用户问题）都必须走它，
否则两边用的模型或维度不一致，算出来的相似度没有任何意义。
"""

from langchain_core.embeddings import Embeddings

from supportflow.core.config import settings

# text-embedding-v4 单次最多 10 条，超过会被接口直接拒掉。
BATCH_SIZE = 10


def get_embedding_model() -> Embeddings:
    """造向量模型对象。第一次调用才真正创建，import 本模块不会连网。"""
    from langchain.embeddings import init_embeddings

    return init_embeddings(
        model=settings.EMBEDDING_MODEL,
        provider="openai",
        api_key=settings.DASHSCOPE_API_KEY.get_secret_value(),
        base_url=settings.DASHSCOPE_BASE_URL,
        check_embedding_ctx_length=False,
    )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量，返回顺序与入参一一对应。"""
    if not texts:
        return []

    model = get_embedding_model()
    vectors: list[list[float]] = []
    # 逐批串行发，不并发：灌库是一次性动作，慢一点没关系，出问题好定位。
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        vectors.extend(await model.aembed_documents(batch))
    return vectors


async def embed_query(text: str) -> list[float]:
    """把一句查询转成向量。单走一个入口，保证和文档走的是同一条路。"""
    return (await embed_texts([text]))[0]
