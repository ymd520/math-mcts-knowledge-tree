"""Command-line handoff between ChatGPT-authored math knowledge and Math-MCTS.

No command promotes AI text to a reviewed rule or a proved theorem.
Examples:
  python tools/ai_knowledge_cli.py ingest examples/ai_knowledge_seed_v1.json --db ai.sqlite
  python tools/ai_knowledge_cli.py search 'compact' --db ai.sqlite --limit 10
  python tools/ai_knowledge_cli.py collide --db ai.sqlite --iterations 500
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.ai_knowledge import (
    ingest_file, lookup, all_candidates, inventory, query_for_research,
    collide_for_research,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None,
                   help="Optional global db path (also permitted after command)")
    subs = p.add_subparsers(dest="command", required=True)
    add = subs.add_parser("ingest",help="Atomically store an AI knowledge pack as unreviewed")
    add.add_argument("pack",type=Path)
    srch = subs.add_parser("search",help="Indexed AI candidate search")
    srch.add_argument("query")
    mcts = subs.add_parser("collide",help="Run MCTS on a bounded AI candidate view")
    mcts.add_argument("--seed")
    mcts.add_argument("--iterations",type=int,default=300)
    subs.add_parser("inventory",help="Candidate-only counts")
    subs.add_parser("list",help="Inspect entries (unreviewed)")
    for q in (add,srch,mcts,subs.choices["inventory"],subs.choices["list"]):
        q.add_argument("--db",type=Path,dest="sub_db",default=None)
        q.add_argument("--limit",type=int,default=30)
    args = p.parse_args()
    db = args.sub_db or args.db
    if db is None:
        p.error("Supply --db to prevent accidental writes to curated storage")
    if args.command == "ingest":
        report = ingest_file(db,args.pack)
    elif args.command == "search":
        report = {"source":"unreviewed_ai_generated","results":
                  query_for_research(db,args.query,limit=args.limit,
                                     top_k=min(args.limit,10))}
    elif args.command == "collide":
        report = {"source":"unreviewed_ai_generated",
                  "search_method":"MCTS_cross_domain_candidate_pairs",
                  "results":collide_for_research(db,limit=args.limit,seed=args.seed,
                                                 iterations=args.iterations)}
    elif args.command == "list":
        report = {"status":"unreviewed_ai_generated",
                  "results":all_candidates(db,limit=args.limit)}
    else:
        report = inventory(db)
    print(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
