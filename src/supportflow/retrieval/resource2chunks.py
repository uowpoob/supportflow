"""知识入库入口：读取 Markdown → 按条款切分 → 向量化 → 写入 Milvus。

当前资料每个条款都很短，按完整条款切分即可，不做固定长度截断或重叠。
这是针对仓库中“一级文档标题 + 二级条款标题”格式的解析器。
load_documents / split_documents 仅处理本地文本；显式执行入库才调用外部服务。
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

from langchain_core.documents import Document


RETRIEVAL_DIR = Path(__file__).resolve().parent
DOCUMENT_DIRS = (RETRIEVAL_DIR / "policies", RETRIEVAL_DIR / "data")
SECTION_PATTERN = re.compile(r"^##[ \t]+(.+)$", re.MULTILINE)


def load_documents(directories: tuple[Path, ...] = DOCUMENT_DIRS) -> list[Document]:
    """一份文件对应一个 Document，page_content 是全文，metadata 保存来源。"""
    documents: list[Document] = []
    document_ids: set[str] = set()

    for directory in directories:
        if not directory.is_dir():
            raise FileNotFoundError(f"知识目录不存在：{directory}")
        paths = sorted(directory.glob("*.md"))
        if not paths:
            raise ValueError(f"知识目录中没有 Markdown 文件：{directory}")

        for path in paths:
            content = path.read_text(encoding="utf-8-sig").strip()
            if not content or not content.startswith("# "):
                raise ValueError(f"文档为空或缺少一级标题：{path}")
            if path.stem in document_ids:
                raise ValueError(f"重复的 document_id：{path.stem}")
            document_ids.add(path.stem)
            documents.append(Document(
                page_content=content,
                metadata={
                    "document_id": path.stem,
                    "title": content.splitlines()[0][2:].strip(),
                    "source": f"{directory.name}/{path.name}",
                    "category": directory.name,
                },
            ))

    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """一个条款对应一个片段；文前说明保留为概述，标题随片段进入向量化文本。"""
    chunks: list[Document] = []
    chunk_ids: set[str] = set()

    for document in documents:
        # 去掉一级标题，随后统一为每个片段补回，避免标题重复。
        body = document.page_content.partition("\n")[2].strip()
        headings = list(SECTION_PATTERN.finditer(body))
        sections = [("overview", "概述", body[:headings[0].start()] if headings else body)]

        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
            section_title = heading.group(1).strip()
            # 用条款编号生成 ID，插入其他条款后已有编号不会因位置变化而改变。
            number = re.match(r"\d+(?:\.\d+)*(?=\s|$)", section_title)
            section_id = number.group() if number else f"section-{index + 1}"
            sections.append((section_id, section_title, body[heading.end():end]))

        for section_id, section_title, content in sections:
            content = content.strip()
            if not content:
                continue
            chunk_id = f"{document.metadata['document_id']}#{section_id}"
            if chunk_id in chunk_ids:
                raise ValueError(f"重复的 chunk_id：{chunk_id}")
            chunk_ids.add(chunk_id)
            chunks.append(Document(
                page_content=f"# {document.metadata['title']}\n\n## {section_title}\n\n{content}",
                metadata={
                    **document.metadata,
                    "chunk_id": chunk_id,
                    "section": section_title,
                },
            ))

    return chunks


async def ingest_documents(directories: tuple[Path, ...] = DOCUMENT_DIRS) -> dict[str, int]:
    """导入当前文件的全部片段；重复运行更新同 ID，不清理源文件中已删除的条款。"""
    from supportflow.core.config import settings
    from supportflow.retrieval.embedding import embed_texts
    from supportflow.retrieval.milvus import init_milvus, upsert_chunks

    documents = load_documents(directories)
    chunks = split_documents(documents)
    if not chunks:
        raise ValueError("没有可入库的正文片段")
    if not settings.DASHSCOPE_API_KEY.get_secret_value().strip():
        raise ValueError("请先配置 DASHSCOPE_API_KEY")

    print(f"读取 {len(documents)} 份文档，切分为 {len(chunks)} 个片段", flush=True)
    # 先检查集合结构，再消耗向量 API；同步 Milvus SDK 放到线程中运行。
    client = await asyncio.to_thread(init_milvus)
    try:
        print(f"正在向量化：{settings.EMBEDDING_MODEL} / {settings.EMBEDDING_DIM} 维", flush=True)
        vectors = await embed_texts([chunk.page_content for chunk in chunks])
        written = await asyncio.to_thread(upsert_chunks, client, chunks, vectors)

        # 按本次 ID 核对可见记录数，不把集合中原有的其他文档算进来。
        chunk_ids = [chunk.metadata["chunk_id"] for chunk in chunks]
        counts = await asyncio.to_thread(
            client.query,
            collection_name=settings.COLLECTION,
            filter=f"chunk_id in {json.dumps(chunk_ids, ensure_ascii=False)}",
            output_fields=["count(*)"],
            consistency_level="Strong",
        )
        stored = counts[0]["count(*)"]
        if stored != len(chunks):
            raise RuntimeError(f"入库校验失败：期望 {len(chunks)} 条，查询到 {stored} 条")
        return {"documents": len(documents), "chunks": len(chunks), "upserted": written, "verified": stored}
    finally:
        await asyncio.to_thread(client.close)


def main() -> None:
    parser = argparse.ArgumentParser(description="将本地知识文档向量化并写入 Milvus")
    parser.add_argument("--dry-run", action="store_true", help="只读取、切分，不调用模型或数据库")
    args = parser.parse_args()
    if args.dry_run:
        documents = load_documents()
        chunks = split_documents(documents)
        print(f"读取 {len(documents)} 份文档，切分为 {len(chunks)} 个片段（未入库）")
        return
    summary = asyncio.run(ingest_documents())
    print(f"入库完成：{json.dumps(summary, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
