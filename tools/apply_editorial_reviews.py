"""Apply source-locked *explicit* editorial decisions, never automatic labels.

Run after build_search_index.py, register_source_statements.py,
and classify_knowledge.py.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.editorial import apply_review_decisions,reviewer_coverage


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--decisions",type=Path,help="Manually reviewed JSON list")
    p.add_argument("--output",type=Path,default=Path("editorial_coverage.json"))
    args=p.parse_args()
    result=None
    if args.decisions:
        records=json.loads(args.decisions.read_text(encoding="utf-8"))
        result=apply_review_decisions(args.db,records)
    report={"applied":result,"coverage":reviewer_coverage(args.db)}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                           encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))


if __name__=="__main__":
    main()
