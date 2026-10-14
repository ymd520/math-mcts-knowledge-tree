"""100k knowledge quality triage and deterministic review case export.

Run after index build, source registration, and classification.
No row is automatically elevated to important/core or a difficulty level.
"""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.review_quality import review_signals, review_queue


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--report", type=Path, default=Path("quality_triage_report.json"))
    p.add_argument("--output", type=Path, default=Path("quality_review_top1000.jsonl.gz"))
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--mode", choices=["priority", "anomaly", "duplicate"], default="priority")
    p.add_argument("--read-only", action="store_true")
    args = p.parse_args()
    result = None if args.read_only else review_signals(args.db)
    if result is not None:
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                          sort_keys=True) + "\n", encoding="utf-8")
    cases = review_queue(args.db, limit=args.limit, mode=args.mode)
    with gzip.open(args.output, "wt", encoding="utf-8") as out:
        for row in cases:
            out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"report": result, "cases_exported": len(cases),
                      "mode": args.mode}, ensure_ascii=False))


if __name__ == "__main__":
    main()
