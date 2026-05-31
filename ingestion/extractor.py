"""PDF text + table extraction."""
from dataclasses import dataclass
import re
import fitz  # PyMuPDF


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


def extract_pages(pdf_path: str) -> list[PageText]:
    """Extract cleaned text one page at a time, preserving 1-based page numbers."""
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        text = _clean_page(page.get_text("text"))
        if text:
            pages.append(PageText(page_number=page.number + 1, text=text))
    doc.close()
    return pages


def extract_text(pdf_path: str) -> str:
    return "\n".join(page.text for page in extract_pages(pdf_path))


def _clean_page(text: str) -> str:
    # Fix hyphenated line breaks
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
    # Normalize whitespace
    text = re.sub(r" {2,}", " ", text)
    # Remove page numbers at start of line (e.g. "2 " or "12 ")
    text = re.sub(r"^\d{1,3}\s+", "", text, flags=re.MULTILINE)
    # Remove trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    # Drop blank lines at start/end
    text = "\n".join(lines).strip()
    return text


def extract_tables_as_text(pdf_path: str) -> list[str]:
    """Extract tables with camelot, convert to pipe-delimited text."""
    try:
        import camelot
        tables = camelot.read_pdf(pdf_path, pages="all", flavor="lattice")
        result = []
        for table in tables:
            df = table.df
            rows = df.values.tolist()
            pipe_rows = [" | ".join(str(cell).strip() for cell in row) for row in rows]
            result.append("\n".join(pipe_rows))
        return result
    except Exception:
        return []
