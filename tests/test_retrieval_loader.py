"""离线验证来源可追溯、正文不丢失，以及条款 ID 的稳定性。"""

import pytest

from supportflow.retrieval.resource2chunks import load_documents, split_documents


def test_load_and_split_preserve_content_and_context(tmp_path):
    path = tmp_path / "PRD-001.md"
    path.write_text(
        "\ufeff# 示例耳机\n\n适用于第一代。\n\n"
        "## 1.1 连接\n\n先打开蓝牙。\n\n再选择设备。\n\n"
        "## 1.2 维护\n\n### 注意事项\n\n不要进水。\n",
        encoding="utf-8",
    )
    documents = load_documents((tmp_path,))
    chunks = split_documents(documents)

    assert len(documents) == 1
    assert [c.metadata["chunk_id"] for c in chunks] == [
        "PRD-001#overview", "PRD-001#1.1", "PRD-001#1.2",
    ]
    assert "适用于第一代。" in chunks[0].page_content
    assert "先打开蓝牙。\n\n再选择设备。" in chunks[1].page_content
    assert "### 注意事项\n\n不要进水。" in chunks[2].page_content
    assert all(c.page_content.startswith("# 示例耳机\n") for c in chunks)
    assert all(c.metadata["source"] == f"{tmp_path.name}/PRD-001.md" for c in chunks)
    assert "chunk_id" not in documents[0].metadata

    # 新增较早的条款不会改变既有条款的 ID 或内容。
    path.write_text(path.read_text(encoding="utf-8").replace(
        "## 1.1", "## 1.0 准备\n\n准备手机。\n\n## 1.1",
    ), encoding="utf-8")
    updated = {c.metadata["chunk_id"]: c for c in split_documents(load_documents((tmp_path,)))}
    assert updated["PRD-001#1.1"] == chunks[1]


def test_document_without_sections_becomes_overview(tmp_path):
    (tmp_path / "note.md").write_text("# 说明\n\n完整说明。", encoding="utf-8")
    chunks = split_documents(load_documents((tmp_path,)))
    assert len(chunks) == 1
    assert chunks[0].metadata["section"] == "概述"
    assert chunks[0].page_content.endswith("完整说明。")


def test_duplicate_clause_ids_are_rejected(tmp_path):
    (tmp_path / "bad.md").write_text(
        "# 政策\n\n## 1.1 条款甲\n\n甲。\n\n## 1.1 条款乙\n\n乙。",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重复的 chunk_id"):
        split_documents(load_documents((tmp_path,)))


def test_missing_empty_and_malformed_sources_are_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_documents((tmp_path / "missing",))
    with pytest.raises(ValueError, match="没有 Markdown"):
        load_documents((tmp_path,))
    (tmp_path / "bad.md").write_text("没有标题", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少一级标题"):
        load_documents((tmp_path,))
