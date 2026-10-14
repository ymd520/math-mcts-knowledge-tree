"""Build a reproducible source-candidate search index, without grade inflation.

Usage:
  python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
  python tools/build_search_index.py --db math_index.sqlite --query "Fourier transform"
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.fast_index import build_index, fast_search, index_stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path("math_index.sqlite"))
    p.add_argument("--candidate-limit", type=int, default=100000)
    p.add_argument("--curated-only", action="store_true")
    p.add_argument("--query")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--summary", type=Path)
    args = p.parse_args()
    if args.query:
        print(json.dumps({"results": fast_search(args.db, args.query, top_k=args.top_k)},
                         ensure_ascii=False, indent=2))
        return
    report = build_index(args.db, candidate_limit=args.candidate_limit,
                         include_imported=not args.curated_only)
    report["index"] = index_stats(args.db)
    if args.summary:
        args.summary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
