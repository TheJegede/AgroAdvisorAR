"""PDF text + table extraction using IBM Docling."""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

import sys
import torch
import pypdfium2 as pdfium
import subprocess
import argparse
from pathlib import Path

# Limit threads on Windows/CPU environments to prevent OOM / segfault crashes
torch.set_num_threads(1)

from dataclasses import dataclass
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str


def _get_converter() -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    # TableFormer disabled — its ~770-param model causes OOM/segfault on
    # CPU-only Windows.  Docling still extracts table *text* in reading order,
    # just not as markdown grids.  Re-enable once a GPU host is available.
    pipeline_options.do_table_structure = False
    # Force CPU — Docling's default device='auto' tries CUDA and crashes on
    # Windows when GPU memory is insufficient or CUDA state is corrupt.
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=1,
        device="cpu",
    )
    
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                backend=PyPdfiumDocumentBackend
            )
        }
    )


def extract_text(pdf_path: str) -> str:
    """Extract unified Markdown text from PDF using Docling in chunked page ranges via subprocesses to prevent memory leaks and crashes."""
    doc = pdfium.PdfDocument(pdf_path)
    total_pages = len(doc)
    doc.close()
    
    chunk_size = 10
    markdown_parts = []
    
    # We use a temporary directory in the workspace to save temporary markdown files
    temp_dir = Path(__file__).resolve().parent / "temp_markdown"
    temp_dir.mkdir(exist_ok=True)
    
    for start in range(1, total_pages + 1, chunk_size):
        end = min(start + chunk_size - 1, total_pages)
        temp_file = temp_dir / f"temp_{start}_{end}.md"
        
        # Build the command using sys.executable to run the chunk in a subprocess
        cmd = [
            sys.executable,
            __file__,
            "--pdf", str(pdf_path),
            "--start", str(start),
            "--end", str(end),
            "--out", str(temp_file)
        ]
        
        print(f"  [Docling Subprocess] Converting pages {start} to {end} of {total_pages}...")
        try:
            # Don't use check=True — tqdm writes progress bars to stderr, and
            # Windows PowerShell treats any stderr output as exit-code 1.
            # Instead, check success by whether the output file was created.
            result = subprocess.run(cmd, capture_output=True, text=True)
            if temp_file.exists():
                with open(temp_file, "r", encoding="utf-8") as f:
                    md_part = f.read()
                if md_part.strip():
                    markdown_parts.append(md_part)
                temp_file.unlink()
            else:
                print(f"  [Docling Subprocess] Warning: No output for pages {start}-{end}")
                if result.stderr:
                    print(f"    STDERR: {result.stderr[-500:]}")
        except Exception as e:
            print(f"  [Docling Subprocess] Error converting pages {start}-{end}: {e}")
            
    # Clean up temp_dir if empty
    try:
        temp_dir.rmdir()
    except Exception:
        pass
        
    return "\n\n".join(markdown_parts)


def extract_pages(pdf_path: str) -> list[PageText]:
    """Extract page text using Docling."""
    md_content = extract_text(pdf_path)
    return [PageText(page_number=1, text=md_content)]


def extract_tables_as_text(pdf_path: str) -> list[str]:
    """Legacy helper. Since Docling integrates tables directly into the markdown output,
    we return an empty list here to avoid double-processing table content."""
    return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    
    try:
        converter = _get_converter()
        result = converter.convert(args.pdf, page_range=(args.start, args.end))
        md_text = result.document.export_to_markdown()
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md_text)
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
