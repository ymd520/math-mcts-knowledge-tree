"""Generate per-knowledge source credits and a report; never claim discoveries."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.attribution import build_attribution_index, attribution_by_id


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--report",type=Path,default=Path("source_attribution_report.json"))
    p.add_argument("--id",help="Inspect one knowledge card's precise credit status")
    args=p.parse_args()
    if args.id:
        result=attribution_by_id(args.db,args.id)
        if result is None: raise SystemExit("Unknown/unindexed source ID")
    else:
        result=build_attribution_index(args.db)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
