"""document_chunk 模块测试。"""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from knowledge.ingest.document_chunk import chunkDocuments


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "md"


def testChunkDocumentsShouldKeepShortDocumentAsSingleChunk() -> None:
    """短文本应保持单块，避免标题式内容被过度切分。"""

    documents = [Document(page_content="短内容。", metadata={"source": "short.md"})]

    chunks = chunkDocuments(documents)

    assert len(chunks) == 1
    assert chunks[0].metadata["chunk_index"] == 0
    assert chunks[0].metadata["chunk_count"] == 1
    assert chunks[0].metadata["char_count"] == len("短内容。")


def testChunkDocumentsShouldPopulateChunkMetadata() -> None:
    """切分结果应补齐分片级 metadata。"""

    longText = (
        "第一段内容比较长，用来制造足够的上下文差异。"
        "第二段继续展开说明，保证句子数量足够多。"
        "\n\n"
        "## 小节标题\n\n"
        "第三段继续描述不同主题，让语义边界更明显。"
        "第四段补充更多细节，帮助切分器做出判断。"
    )
    documents = [Document(page_content=longText, metadata={"source": "long.md"})]

    chunks = chunkDocuments(documents)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.metadata["source"] == "long.md"
        assert "chunk_index" in chunk.metadata
        assert "chunk_count" in chunk.metadata
        assert "char_count" in chunk.metadata


def testChunkDocumentsShouldPreserveMarkdownHeaderMetadata() -> None:
    """真实 Markdown 文档的标题应被提取到 metadata。"""

    documentPath = DATA_DIR / "rag.md"
    documents = [
        Document(
            page_content=documentPath.read_text(encoding="utf-8"),
            metadata={"source": str(documentPath)},
        )
    ]

    chunks = chunkDocuments(documents)

    assert len(chunks) > 1
    assert any("header_1" in chunk.metadata for chunk in chunks)
    assert any("header_2" in chunk.metadata for chunk in chunks)


def testChunkDocumentsShouldReadRealMarkdownFile() -> None:
    """应能直接处理 data 目录中的真实 Markdown 文档。"""

    documentPath = DATA_DIR / "multi-agent.md"
    documents = [
        Document(
            page_content=documentPath.read_text(encoding="utf-8"),
            metadata={"source": str(documentPath)},
        )
    ]

    chunks = chunkDocuments(documents)

    assert len(chunks) > 10
    assert all(chunk.metadata["source"] == str(documentPath) for chunk in chunks)
    assert all(chunk.metadata["char_count"] > 0 for chunk in chunks)


def testChunkDocumentsShouldSplitOversizedSectionWithFallbackSplitter() -> None:
    """超长 Markdown 段落应继续切分，避免单块过大。"""

    body = "这是正文内容。" * 500
    documents = [
        Document(
            page_content=f"# 一级标题\n\n## 超长章节\n\n{body}",
            metadata={"source": "oversized.md"},
        )
    ]

    chunks = chunkDocuments(documents)

    assert len(chunks) > 1
    assert all(chunk.metadata["header_1"] == "一级标题" for chunk in chunks)
    assert all(chunk.metadata["header_2"] == "超长章节" for chunk in chunks)
