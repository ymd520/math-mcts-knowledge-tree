"""Candidate ingestion, retrieval, evidence audit and MCTS method proposals.

Examples:
  python tools/expand_knowledge.py import --db external_math.sqlite --input afp.jsonl.gz
  python tools/expand_knowledge.py inventory --db external_math.sqlite
  python tools/expand_knowledge.py search --db external_math.sqlite --query 'finite group'
  python tools/expand_knowledge.py methods --goal 'noncommutative convolution upper bound'
  python tools/expand_knowledge.py coverage --index math_index.sqlite
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.method_library import all_operators, recommend
from math_mcts.research_prioritizer import prioritize
from math_mcts.source_expansion import (
    import_jsonl, inventory, mathlib_review_snapshot, search,
)


def coverage(index: Path) -> dict:
    report = mathlib_review_snapshot(index)
    manifest = Path(__file__).resolve().parents[1] / "math_mcts/data/imported/manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        total = data["imported_cards"]
        report["original_imported_records"] = total
        report["indexed_fraction_of_original"] = (report["indexed_unreviewed_import"] / total
                                                   if total else 0.0)
        report["original_not_in_index"] = total - report["indexed_unreviewed_import"]
        if report["original_not_in_index"] < 0:
            raise ValueError("Index exceeds original import count")
    report["coverage_not_proof_or_importance"] = True
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    cmd = p.add_subparsers(dest="command", required=True)
    imp = cmd.add_parser("import", help="Import a user-supplied licensed source manifest")
    imp.add_argument("--db", type=Path, default=Path("external_math.sqlite"))
    imp.add_argument("--input", type=Path, required=True)
    imp.add_argument("--max-records", type=int, default=1000000)
    view = cmd.add_parser("search", help="Search external UNREVIEWED statements")
    view.add_argument("--db", type=Path, default=Path("external_math.sqlite"))
    view.add_argument("--query", required=True)
    view.add_argument("--limit", type=int, default=20)
    inv = cmd.add_parser("inventory", help="Actual external source counts")
    inv.add_argument("--db", type=Path, default=Path("external_math.sqlite"))
    methods = cmd.add_parser("methods", help="Suggest falsifiable mathematical actions")
    methods.add_argument("--goal")
    methods.add_argument("--obstacles", default="")
    methods.add_argument("--category")
    methods.add_argument("--limit", type=int, default=15)
    rank = cmd.add_parser("prioritize", help="Rank source candidates for mathematical review")
    rank.add_argument("--index", type=Path, default=Path("math_index.sqlite"))
    rank.add_argument("--focus", required=True)
    rank.add_argument("--domain")
    rank.add_argument("--limit", type=int, default=50)
    stats = cmd.add_parser("coverage", help="Audit existing mathlib candidate coverage")
    stats.add_argument("--index", type=Path, default=Path("math_index.sqlite"))
    args = p.parse_args()
    if args.command == "import":
        result = import_jsonl(args.db, args.input, max_records=args.max_records)
    elif args.command == "search":
        result = search(args.db, args.query, limit=args.limit)
    elif args.command == "inventory":
        result = inventory(args.db)
    elif args.command == "methods":
        result = (recommend(args.goal, obstacles=args.obstacles, limit=args.limit,
                            category=args.category)
                  if args.goal else [x.__dict__ for x in all_operators()])
    elif args.command == "prioritize":
        result = prioritize(args.index, args.focus, limit=args.limit, domain=args.domain)
    else:
        result = coverage(args.index)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
