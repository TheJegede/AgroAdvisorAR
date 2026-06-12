"""Chunk documents and attach metadata using a Markdown/Layout-aware strategy."""
import hashlib
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# Define headers to split on
headers_to_split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]

_markdown_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=headers_to_split_on,
    strip_headers=False,  # Keep headers in text so the LLM sees the structure
)

_recursive_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_document(
    text: str,
    *,
    document_title: str,
    source_url: str,
    crop_type: str,
    pub_year: int | None = None,
    section_heading: str = "",
) -> list[Document]:
    # 1. Split by Markdown Headers first to isolate structural sections
    md_header_splits = _markdown_splitter.split_text(text)

    documents = []
    chunk_idx = 0
    for split_doc in md_header_splits:
        # Determine the section heading from the headers
        headers = []
        for h_key in ("Header 1", "Header 2", "Header 3"):
            h_val = split_doc.metadata.get(h_key)
            if h_val:
                headers.append(h_val)
        current_section = " - ".join(headers) if headers else section_heading

        # 2. Split recursively if the section exceeds our chunk size
        sub_chunks = _recursive_splitter.split_text(split_doc.page_content)

        for sub_chunk in sub_chunks:
            # Generate a deterministic hash for the chunk ID
            chunk_id = hashlib.sha256(
                f"{document_title}:{chunk_idx}:{sub_chunk[:50]}".encode()
            ).hexdigest()[:16]

            meta = {
                "chunk_id": chunk_id,
                "document_title": document_title,
                "source_url": source_url,
                "crop_type": crop_type,
                "section_heading": current_section,
                "chunk_index": chunk_idx,
            }
            if pub_year is not None:
                meta["pub_year"] = pub_year

            doc = Document(page_content=sub_chunk, metadata=meta)
            documents.append(doc)
            chunk_idx += 1

    return documents
