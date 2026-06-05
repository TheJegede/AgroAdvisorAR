"""Audit soybeans-namespace eval items for off-crop content.

Classifies each soybeans item by QUERY INTENT using DeepInfra LLM:
  soybeans — query is specifically about soybean agronomy/pests/varieties
  general  — weed management, pine, wheat, rice, cotton, corn, pasture, equipment, etc.

Writes evals/eval_set_v2_relabeled.jsonl with updated namespace fields.

Usage:
  cd evals
  python audit_namespace.py [--dry-run]
"""
import os, sys, json, argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

EVAL_SET   = Path(__file__).parent / "eval_set_v2.jsonl"
OUT_PATH   = Path(__file__).parent / "eval_set_v2_relabeled.jsonl"

SYSTEM = (
    "You classify queries for an Arkansas agricultural advisory RAG system. "
    "The system has namespaces: soybeans, rice, poultry, general.\n\n"
    "Classify the query's PRIMARY TOPIC for retrieval routing.\n"
    "Reply with ONLY one word: soybeans OR general\n\n"
    "soybeans = query is specifically about soybean planting, soybean seeding rates, "
    "soybean varieties/traits, soybean diseases, soybean-specific herbicide programs, "
    "soybean yields, or soybean storage.\n"
    "general  = weed/brush management across crops, farm equipment (sprayer calibration), "
    "soil/irrigation, pine/forestry, wheat, cotton, corn, rice, pasture, vegetables, "
    "or any topic where soybeans are NOT the primary subject."
)

USER_TEMPLATE = """QUERY: {query}

GOLD PASSAGE (first 250 chars):
{chunk_text}

DOCUMENT TITLE: {document_title}

Reply ONLY: soybeans OR general"""


def classify_item(llm: ChatOpenAI, item: dict) -> str:
    resp = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=USER_TEMPLATE.format(
            query=item["query"],
            chunk_text=item.get("chunk_text", "")[:250],
            document_title=item.get("document_title", "unknown"),
        )),
    ])
    label = (resp.content or "").strip().lower()
    # normalise: accept any response containing soybeans or general
    if "soybeans" in label:
        return "soybeans"
    if "general" in label:
        return "general"
    # fallback: keep original if LLM returns garbage
    return item["namespace"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print classifications without writing output file")
    args = ap.parse_args()

    llm = ChatOpenAI(
        model=os.environ.get("DEEPINFRA_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        openai_api_key=os.environ["DEEPINFRA_API_KEY"],
        openai_api_base="https://api.deepinfra.com/v1",
        temperature=0,
    )

    items = [json.loads(l) for l in open(EVAL_SET, encoding="utf-8")]
    soy_items = [(i, it) for i, it in enumerate(items) if it["namespace"] == "soybeans"]

    print(f"Auditing {len(soy_items)} soybeans items...\n")
    print(f"{'idx':>4} {'new_ns':>9}  query (first 65 chars)")
    print("-" * 82)

    changes = 0
    for idx, item in soy_items:
        new_ns = classify_item(llm, item)
        marker = " <-" if new_ns != item["namespace"] else ""
        if new_ns != item["namespace"]:
            changes += 1
        print(f"{idx:>4} {new_ns:>9}{marker}  {item['query'][:65]}")
        item["namespace"] = new_ns

    print(f"\nTotal relabeled: {changes} / {len(soy_items)}")
    print(f"  soybeans -> general: {changes}")
    print(f"  unchanged: {len(soy_items) - changes}")

    ns_counts = {}
    for it in items:
        ns_counts[it["namespace"]] = ns_counts.get(it["namespace"], 0) + 1
    print(f"\nNew namespace distribution: {ns_counts}")

    if not args.dry_run:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it) + "\n")
        print(f"\nWrote {OUT_PATH}")
    else:
        print("\n[dry-run] Output file NOT written.")


if __name__ == "__main__":
    main()
