"""Chunk documents and attach metadata."""
import hashlib
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Size chunks by TOKENS, not characters. The old splitter used length_function=len
# (characters): chunk_size=512 chars produced ~100-token chunks — ¼ of gte-base's
# 512-token input budget — fragmenting each answer across many near-duplicate
# vectors and starving retrieval recall (measured hit@5 0.25). tiktoken cl100k is
# used for the length function (not the gte/BERT tokenizer) because this env
# segfaults loading torch/transformers under pytest; tiktoken BPE counts run lower
# than gte wordpiece, so 400 tokens stays safely under the 512 limit (gte
# tail-truncates anyway).
CHUNK_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 50

_splitter = None


def _get_splitter():
    global _splitter
    if _splitter is None:
        _splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name="cl100k_base",
            chunk_size=CHUNK_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    return _splitter


def chunk_document(
    text: str,
    *,
    document_title: str,
    source_url: str,
    crop_type: str,
    pub_year: int | None = None,
    section_heading: str = "",
) -> list[Document]:
    chunks = _get_splitter().split_text(text)
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
