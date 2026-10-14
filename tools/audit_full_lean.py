"""Strict global extraction progress report and optional incremental import."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.full_lean_coverage import audit_full_extraction
from math_mcts.full_lean_import import ingest_full_receipts,indexed_type_conditions


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--receipts",type=Path,required=True)
    p.add_argument("--report",type=Path,default=Path("full_lean_coverage.json"))
    p.add_argument("--require-complete",action="store_true")
    p.add_argument("--db",type=Path)
    p.add_argument("--type-id")
    args=p.parse_args()
    report=audit_full_extraction(args.plan,args.receipts,
                                 require_complete=False)
    if args.db:
        report["import"]=ingest_full_receipts(args.db,args.plan,args.receipts)
        if args.type_id:
            report["type_profile"]=indexed_type_conditions(args.db,args.type_id)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))
    if args.require_complete and not report["complete"]:
        raise SystemExit("Incomplete Lean extraction - see exact uncovered counts")


if __name__=="__main__":
    main()
