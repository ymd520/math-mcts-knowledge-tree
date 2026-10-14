"""Export a complete credited, type-aware but UNREVIEWED mathematics queue."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.review_backlog import export_review_backlog


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("full_source_review_backlog.jsonl.gz"))
    p.add_argument("--report",type=Path,default=Path("full_source_review_backlog_report.json"))
    a=p.parse_args()
    result=export_review_backlog(a.db,a.output)
    a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
