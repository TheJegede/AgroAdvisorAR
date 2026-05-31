"""Chunk documents and attach metadata."""
import hashlib
import re
from dataclasses import dataclass
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

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(\.\d+)*|[A-Z])[\.)]\s+\S+")
_TABLEISH_RE = re.compile(r"^[\d\s\W_]+$")
_COMMON_SHORT_HEADINGS = {
    "abstract",
    "acknowledgment",
    "acknowledgments",
    "background",
    "conclusion",
    "conclusions",
    "discussion",
    "introduction",
    "materials",
    "methods",
    "references",
    "results",
    "summary",
}
_COMMON_HEADING_TERMS = {
    "application",
    "calibration",
    "control",
    "disease",
    "fertility",
    "harvest",
    "herbicide",
    "insect",
    "irrigation",
    "management",
    "nitrogen",
    "planting",
    "production",
    "recommendations",
    "safety",
    "soil",
    "variety",
    "water",
    "weed",
}
_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "among",
    "because",
    "before",
    "being",
    "between",
    "could",
    "during",
    "fields",
    "first",
    "from",
    "general",
    "into",
    "more",
    "most",
    "other",
    "over",
    "rice",
    "should",
    "than",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "under",
    "using",
    "when",
    "where",
    "which",
    "while",
    "with",
    "within",
    "would",
}


@dataclass(frozen=True)
class SourcePage:
    page_number: int
    text: str


@dataclass(frozen=True)
class SectionBlock:
    heading: str
    text: str
    page_start: int | None
    page_end: int | None
    parent_section_id: str


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


def infer_pub_year(*values: str) -> int | None:
    years: list[int] = []
    for value in values:
        years.extend(int(match.group(0)) for match in _YEAR_RE.finditer(value or ""))
    return max(years) if years else None


def make_doc_id(document_title: str, source_url: str = "") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", document_title.lower()).strip("-")[:64]
    digest = hashlib.sha256(f"{document_title}:{source_url}".encode()).hexdigest()[:10]
    return f"{slug}-{digest}" if slug else digest


def split_section_blocks(pages: list[SourcePage]) -> list[SectionBlock]:
    """Heuristic section splitter for Extension PDFs.

    This intentionally stays deterministic and conservative. It promotes only
    likely heading lines, preserving page ranges so downstream retrieval can
    assemble parent-section context and cite page/section metadata.
    """
    sections: list[SectionBlock] = []
    current_heading = "Document"
    current_lines: list[str] = []
    page_start: int | None = pages[0].page_number if pages else None
    page_end: int | None = page_start

    def flush() -> None:
        nonlocal current_lines, page_start, page_end
        text = "\n".join(line for line in current_lines if line.strip()).strip()
        if not text:
            return
        sections.append(SectionBlock(
            heading=current_heading,
            text=text,
            page_start=page_start,
            page_end=page_end,
            parent_section_id="",
        ))
        current_lines = []

    for page in pages:
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if _is_heading_line(line):
                flush()
                current_heading = line
                page_start = page.page_number
                page_end = page.page_number
                continue
            if not current_lines:
                page_start = page.page_number if page_start is None else page_start
            page_end = page.page_number
            current_lines.append(line)
    flush()

    if not sections and pages:
        text = "\n".join(page.text for page in pages).strip()
        sections = [SectionBlock(
            heading="Document",
            text=text,
            page_start=pages[0].page_number,
            page_end=pages[-1].page_number,
            parent_section_id="",
        )]

    return [
        SectionBlock(
            heading=section.heading,
            text=section.text,
            page_start=section.page_start,
            page_end=section.page_end,
            parent_section_id=_section_id(section.heading, section.page_start),
        )
        for section in sections
    ]


def chunk_sectioned_document(
    pages: list[SourcePage],
    *,
    document_title: str,
    source_url: str,
    crop_type: str,
    doc_type: str = "extension_pdf",
    pub_year: int | None = None,
) -> list[Document]:
    """Chunk a PDF while preserving title, section, page, and parent metadata."""
    doc_id = make_doc_id(document_title, source_url)
    year = pub_year if pub_year is not None else infer_pub_year(document_title, source_url)
    docs: list[Document] = []

    for section_index, section in enumerate(split_section_blocks(pages)):
        parent_section_id = _section_id(f"{doc_id}:{section.heading}", section.page_start)
        chunks = _splitter.split_text(section.text)
        for chunk_index, chunk in enumerate(chunks):
            chunk_id = hashlib.sha256(
                f"{doc_id}:{parent_section_id}:{chunk_index}:{chunk[:80]}".encode()
            ).hexdigest()[:16]
            retrieval_text = _build_retrieval_text(
                document_title=document_title,
                section_heading=section.heading,
                chunk=chunk,
            )
            retrieval_header = retrieval_text.split("\n", 1)[0]
            metadata = {
                "doc_id": doc_id,
                "document_title": document_title,
                "source_url": source_url,
                "crop_type": crop_type,
                "doc_type": doc_type,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "section_heading": "" if section.heading == "Document" else section.heading,
                "subsection_heading": "",
                "chunk_id": chunk_id,
                "parent_section_id": parent_section_id,
                "section_index": section_index,
                "chunk_index": chunk_index,
                "retrieval_header": retrieval_header,
                "retrieval_text": retrieval_text,
            }
            if year is not None:
                metadata["pub_year"] = year
            docs.append(Document(page_content=chunk, metadata=metadata))
    return docs


def _is_heading_line(line: str) -> bool:
    line = re.sub(r"\s+", " ", line).strip()
    if not (3 <= len(line) <= 90):
        return False
    if _TABLEISH_RE.match(line):
        return False
    numbered = _NUMBERED_HEADING_RE.match(line)
    if any(ch.isdigit() for ch in line) and not numbered:
        return False
    if "," in line and not line.isupper():
        return False
    if "." in line and not numbered and not line.isupper():
        return False
    if line.endswith((".", ",", ";", ":")) and not line.isupper():
        return False
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", line)]
    if not words or len(words) > 12:
        return False
    lower_words = {word.lower() for word in words}
    if numbered:
        body = re.sub(r"^(\d+(\.\d+)*|[A-Z])[\.)]\s+", "", line)
        body_words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", body)]
        body_lower = {word.lower() for word in body_words}
        return (
            2 <= len(body_words) <= 8
            and not body.endswith((".", ",", ";", ":"))
            and bool(body_lower & (_COMMON_HEADING_TERMS | _COMMON_SHORT_HEADINGS))
        )
    if len(words) == 1:
        return words[0].lower() in _COMMON_SHORT_HEADINGS
    if len(words) == 2 and not (lower_words & _COMMON_HEADING_TERMS):
        return False
    if line[:1].islower():
        return False
    alpha = "".join(ch for ch in line if ch.isalpha())
    if alpha and alpha.isupper() and len(alpha) >= 4:
        return True
    titleish = sum(1 for word in words if word[:1].isupper())
    return (
        len(words) <= 9
        and titleish / len(words) >= 0.65
        and bool(lower_words & _COMMON_HEADING_TERMS)
    )


def _section_id(heading: str, page_start: int | None) -> str:
    digest = hashlib.sha256(f"{heading}:{page_start}".encode()).hexdigest()[:10]
    return f"section-{digest}"


def _build_retrieval_text(*, document_title: str, section_heading: str, chunk: str) -> str:
    header = _build_retrieval_header(
        document_title=document_title,
        section_heading=section_heading,
        chunk=chunk,
    )
    return f"{header}\n\n{chunk}"


def _build_retrieval_header(*, document_title: str, section_heading: str, chunk: str) -> str:
    """Build concise deterministic context for embedding/sparse retrieval."""
    parts = [document_title]
    if section_heading and section_heading != "Document":
        parts.append(section_heading)
    summary = _chunk_context_summary(chunk)
    if summary:
        parts.append(summary)
    return " | ".join(parts)


def _chunk_context_summary(chunk: str, max_chars: int = 180) -> str:
    content_lines = _content_lines(chunk)
    clean = re.sub(r"\s+", " ", " ".join(content_lines) or chunk).strip()
    if not clean:
        return ""

    terms = _salient_terms(clean)
    sentence = _first_sentence(clean)
    if terms and sentence:
        summary = f"{', '.join(terms)} - {sentence}"
    else:
        summary = sentence or ", ".join(terms)
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 1].rstrip(" ,.;:-") + "."


def _first_sentence(text: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if len(sentence) >= 30 and not _TABLEISH_RE.match(sentence):
            return sentence.rstrip(".")
    return text[:120].rstrip(" .")


def _salient_terms(text: str, limit: int = 4) -> list[str]:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text)
        if word.lower() not in _STOPWORDS
    ]
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], words.index(item[0])))
    return [word for word, _count in ranked[:limit]]


def _content_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line and not _looks_like_byline(line)]


def _looks_like_byline(line: str) -> bool:
    lower = line.lower()
    if lower.startswith(("u of a ", "university of ", "division of ag")):
        return True
    if len(line) > 140 or "," not in line:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", line)
    if len(words) < 4:
        return False
    titleish = sum(1 for word in words if word[:1].isupper())
    return titleish / len(words) >= 0.75 and not ({w.lower() for w in words} & _COMMON_HEADING_TERMS)
