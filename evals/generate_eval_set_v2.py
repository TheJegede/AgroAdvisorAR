"""
Generate 200-item eval set for round-2 fine-tuning.

Same logic as generate_eval_set.py but:
  - 200 items (rice 110, soybeans 70, poultry 20)
  - random.seed(43)  <- different sample than v1
  - outputs evals/eval_set_v2.jsonl

Run: python evals/generate_eval_set_v2.py
"""
import sys, os, json, random, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))
from extractor import extract_text
from chunker import chunk_document

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
RAW_PDFS_DIR = Path(__file__).parent.parent / "ingestion" / "raw_pdfs"
OUTPUT_PATH = Path(__file__).parent / "eval_set_v2.jsonl"

TARGET_PER_NAMESPACE = {"rice": 110, "soybeans": 70, "poultry": 20}
MIN_CHUNK_LEN = 200

PROMPT = """You are simulating an Arkansas farmer asking for agricultural advice.
Given this excerpt from a University of Arkansas Extension publication:

{chunk_text}

Write ONE question that a real farmer might ask that this text would help answer.
Rules:
- Write as a working farmer, not a researcher
- Use plain language: describe symptoms, observations, field problems
- Do NOT use the document's exact wording or scientific terminology
- Keep it under 80 words

Return only the question. Nothing else."""


def _infer_namespace(filename: str) -> str:
    name = filename.lower()
    for crop in ["rice", "soybeans", "poultry"]:
        if name.startswith(crop):
            return crop
    return "general"


def main():
    random.seed(43)

    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        groq_api_key=GROQ_API_KEY,
        temperature=0.4,
    )

    chunks_by_ns: dict[str, list] = {"rice": [], "soybeans": [], "poultry": []}

    pdf_files = list(RAW_PDFS_DIR.glob("*.pdf"))
    print(f"Chunking {len(pdf_files)} PDFs...")

    for pdf_path in pdf_files:
        ns = _infer_namespace(pdf_path.name)
        if ns not in chunks_by_ns:
            continue
        try:
            text = extract_text(str(pdf_path))
            title = pdf_path.stem.replace("_", " ").replace("-", " ")
            docs = chunk_document(
                text,
                document_title=title,
                source_url=f"file://{pdf_path.resolve()}",
                crop_type=ns,
            )
            chunks_by_ns[ns].extend(
                d for d in docs if len(d.page_content) >= MIN_CHUNK_LEN
            )
        except Exception as e:
            print(f"  Skip {pdf_path.name}: {e}")

    for ns, chunks in chunks_by_ns.items():
        print(f"  {ns}: {len(chunks)} valid chunks")

    sampled = []
    for ns, target in TARGET_PER_NAMESPACE.items():
        pool = chunks_by_ns[ns]
        sampled.extend(random.sample(pool, min(target, len(pool))))
    random.shuffle(sampled)

    print(f"Generating queries for {len(sampled)} chunks via Groq...")
    results = []

    for i, doc in enumerate(sampled):
        try:
            resp = llm.invoke([HumanMessage(content=PROMPT.format(chunk_text=doc.page_content))])
            query = resp.content.strip()
            results.append({
                "query": query,
                "chunk_id": doc.metadata["chunk_id"],
                "chunk_text": doc.page_content,
                "document_title": doc.metadata["document_title"],
                "namespace": doc.metadata["crop_type"],
            })
        except Exception as e:
            print(f"  Skip chunk {doc.metadata['chunk_id']}: {e}")

        time.sleep(2)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(sampled)} done")

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        for item in results:
            f.write(json.dumps(item) + "\n")

    print(f"\nWrote {len(results)} items -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
