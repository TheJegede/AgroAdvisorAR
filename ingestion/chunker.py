"""Chunk documents and attach metadata."""
import hashlib
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

_splitter = RecursiveCharacterTextSplitter(
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
    chunks = _splitter.split_text(text)
    documents = []
    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.sha256(
            f"{document_title}:{i}:{chunk[:50]}".encode()
        ).hexdigest()[:16]

        meta = {
            "chunk_id": chunk_id,
            "document_title": document_title,
            "source_url": source_url,
            "crop_type": crop_type,
            "section_heading": section_heading,
            "chunk_index": i,
        }
        if pub_year is not None:
            meta["pub_year"] = pub_year

        doc = Document(page_content=chunk, metadata=meta)
        documents.append(doc)
    return documents
