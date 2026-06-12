"""Paired helped/hurt comparison between two answer-eval dumps (joined on query).

Usage: python evals/paired_compare.py evals/_out_A.jsonl evals/_out_B.jsonl
Prints overall means, per-namespace means, and helped/hurt/same per metric
(A = first file = treatment arm, B = second file = control arm)."""
import json
import sys


def load(path):
    return {r["query"]: r for r in map(json.loads, open(path, encoding="utf-8"))}


def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    keys = [q for q in a if q in b]
    print(f"paired n = {len(keys)}  (A={sys.argv[1]}  B={sys.argv[2]})")
    for metric in ("correctness", "faithfulness"):
        ma = sum(a[q][metric] for q in keys) / len(keys)
        mb = sum(b[q][metric] for q in keys) / len(keys)
        helped = [q for q in keys if a[q][metric] > b[q][metric]]
        hurt = [q for q in keys if a[q][metric] < b[q][metric]]
        print(f"{metric}: B {100*mb:.1f}% -> A {100*ma:.1f}%  "
              f"(helped {len(helped)} / hurt {len(hurt)} / same {len(keys)-len(helped)-len(hurt)})")
        for q in hurt:
            print(f"   HURT [{b[q]['namespace']}] {b[q][metric]}->{a[q][metric]} :: {q[:70]}")
    by_ns = {}
    for q in keys:
        by_ns.setdefault(a[q]["namespace"], []).append(q)
    for ns, qs in sorted(by_ns.items()):
        ca = sum(a[q]["correctness"] for q in qs) / len(qs)
        cb = sum(b[q]["correctness"] for q in qs) / len(qs)
        print(f"  {ns:9} n={len(qs):2}  corr B {100*cb:.0f}% -> A {100*ca:.0f}%")


if __name__ == "__main__":
    main()
