"""负责 Markdown 文档结构化切分。"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters.markdown import MarkdownHeaderTextSplitter


HEADERS_TO_SPLIT_ON = [
    ("#", "header_1"),
    ("##", "header_2"),
    ("###", "header_3"),
    ("####", "header_4"),
]


def chunkDocuments(documents: list[Document]) -> list[Document]:
    """按 Markdown 标题切分，必要时再对超长块做稳定二次切分。"""

    headerSplitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    fallbackSplitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", "！", "？", "；", " ", ""],
    )
    chunkedDocuments: list[Document] = []
    for document in documents:
        documentChunks = _chunkSingleDocument(
            document=document,
            headerSplitter=headerSplitter,
            fallbackSplitter=fallbackSplitter,
        )
        chunkedDocuments.extend(documentChunks)
    return chunkedDocuments


def _chunkSingleDocument(
    document: Document,
    headerSplitter: MarkdownHeaderTextSplitter,
    fallbackSplitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """先保留 Markdown 结构，再对过大块做二次切分。"""

    headerChunks = headerSplitter.split_text(document.page_content)
    if not headerChunks:
        headerChunks = [Document(page_content=document.page_content, metadata={})]

    expandedChunks: list[Document] = []
    for chunk in headerChunks:
        chunkMetadata = dict(document.metadata)
        chunkMetadata.update(chunk.metadata)
        normalizedChunk = Document(
            page_content=chunk.page_content.strip(),
            metadata=chunkMetadata,
        )
        if not normalizedChunk.page_content:
            continue
        if len(normalizedChunk.page_content) > 1400:
            expandedChunks.extend(fallbackSplitter.split_documents([normalizedChunk]))
        else:
            expandedChunks.append(normalizedChunk)

    if not expandedChunks:
        expandedChunks = [
            Document(
                page_content=document.page_content.strip(),
                metadata=dict(document.metadata),
            )
        ]

    totalChunks = len(expandedChunks)
    normalizedChunks: list[Document] = []
    for chunkIndex, chunk in enumerate(expandedChunks):
        chunkMetadata = dict(chunk.metadata)
        chunkMetadata["chunk_index"] = chunkIndex
        chunkMetadata["chunk_count"] = totalChunks
        chunkMetadata["char_count"] = len(chunk.page_content)
        normalizedChunks.append(Document(page_content=chunk.page_content, metadata=chunkMetadata))
    return normalizedChunks
