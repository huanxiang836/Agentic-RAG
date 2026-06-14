"""document_clean 模块测试。"""

from langchain_core.documents import Document

from knowledge.ingest.document_clean import buildCleanPreview, cleanDocument


def testCleanDocumentShouldRemoveNoiseWithoutDestroyingMarkdown() -> None:
    """应当只清理噪声，不破坏 Markdown 结构。"""

    document = Document(
        page_content="# 标题\u200b  \r\n\r\n\r\n- 列表项  \r\n```python\r\nprint('x')\r\n```\r\n",
        metadata={"source": "demo.md"},
    )

    cleanedDocument = cleanDocument(document)

    assert cleanedDocument.page_content == "# 标题\n\n- 列表项\n```python\nprint('x')\n```"
    assert cleanedDocument.metadata["source"] == "demo.md"
    assert cleanedDocument.metadata["is_cleaned"] is True


def testBuildCleanPreviewShouldContainBeforeAndAfter() -> None:
    """预览文本应同时包含清洗前后内容。"""

    originalDocument = Document(page_content="原始内容\n\n\n第二行", metadata={"source": "demo.md"})
    cleanedDocument = cleanDocument(originalDocument)

    preview = buildCleanPreview(originalDocument, cleanedDocument, maxLength=80)

    assert "文件: demo.md" in preview
    assert "清洗前:" in preview
    assert "清洗后:" in preview
