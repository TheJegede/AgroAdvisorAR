"""Layer A MT bootstrap: translate existing EN corpus chunks to Spanish.

Reads raw PDFs from ingestion/raw_pdfs/, chunks them, translates each chunk with
Helsinki-NLP/opus-mt-en-es, and writes ingestion/es_chunks/corpus_es.jsonl.

Usage:
    python ingestion/translate_corpus.py
    python ingestion/translate_corpus.py --batch-size 32

After translation, ingest with:
    python ingestion/ingest_es_chunks.py
"""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from extractor import extract_text, extract_tables_as_text
from chunker import chunk_document

RAW_PDFS_DIR = Path(__file__).parent / "raw_pdfs"
ES_CHUNKS_DIR = Path(__file__).parent / "es_chunks"
OUTPUT_PATH = ES_CHUNKS_DIR / "corpus_es.jsonl"
CROP_TYPE_PREFIXES = {"rice", "soybeans", "poultry", "general"}


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_TYPE_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def translate_corpus(batch_size: int = 16) -> int:
    import torch
    from transformers import MarianMTModel, MarianTokenizer

    # transformers v5 dropped the "translation" pipeline task, so drive the
    # Marian model directly. GPU when available, else CPU. Override with
    # TRANSLATE_DEVICE (e.g. "cpu", "cuda:1").
    device = os.environ.get("TRANSLATE_DEVICE") or (
        "cuda" if torch.cuda.is_available() else "cpu"
    )
    print(f"Translation device: {device}")

    ES_CHUNKS_DIR.mkdir(exist_ok=True)
    model_name = "Helsinki-NLP/opus-mt-en-es"
    tokenizer = MarianTokenizer.from_pretrained(model_name)
    model = MarianMTModel.from_pretrained(model_name).to(device)
    model.eval()

    def _gen(batch: list[str]) -> list[str]:
        inputs = tokenizer(
            batch, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(device)
        with torch.no_grad():
            # Greedy (num_beams=1): Marian defaults to beam search (~6x memory),
            # which OOMs an 8GB GPU on large batches. Quality loss negligible for MT bootstrap.
            generated = model.generate(**inputs, max_length=512, num_beams=1)
        return tokenizer.batch_decode(generated, skip_special_tokens=True)

    def _translate(batch: list[str]) -> list[str]:
        try:
            return _gen(batch)
        except torch.cuda.OutOfMemoryError:
            # Free fragmented memory, then fall back to one item at a time.
            torch.cuda.empty_cache()
            print(f"  OOM on batch of {len(batch)} — retrying per-item")
            out = []
            for text in batch:
                try:
                    out.extend(_gen([text]))
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    out.extend(_gen_cpu([text]))
            return out

    def _gen_cpu(batch: list[str]) -> list[str]:
        inputs = tokenizer(
            batch, return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        with torch.no_grad():
            generated = model.cpu().generate(**inputs, max_length=512, num_beams=1)
        model.to(device)
        return tokenizer.batch_decode(generated, skip_special_tokens=True)

    pdf_files = sorted(RAW_PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs in {RAW_PDFS_DIR}")
        return 0

    total = 0
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for pdf_path in pdf_files:
            print(f"Translating: {pdf_path.name}")
            try:
                text = extract_text(str(pdf_path))
                tables = extract_tables_as_text(str(pdf_path))
                if tables:
                    text += "\n\n" + "\n\n".join(tables)

                name = pdf_path.stem
                crop_type = _infer_crop_type(pdf_path.name)
                docs = chunk_document(
                    text,
                    document_title=name.replace("_", " ").replace("-", " "),
                    source_url=f"file://{pdf_path.resolve()}",
                    crop_type=crop_type,
                )

                texts = [doc.page_content for doc in docs]
                translated_texts = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    translated_texts.extend(_translate(batch))

                for doc, es_text in zip(docs, translated_texts):
                    record = {
                        **doc.metadata,
                        "text": es_text,
                        "source_lang": "es",
                        "translation_method": "mt",
                        "source_en_chunk_id": doc.metadata.get("chunk_id", ""),
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total += 1

                print(f"  -> {len(docs)} chunks translated")
            except Exception as e:
                print(f"  FAILED: {e}")
            finally:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

    print(f"\nWrote {total} Spanish chunks to {OUTPUT_PATH}")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    translate_corpus(batch_size=args.batch_size)
