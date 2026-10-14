"""Reproducible extraction plan for ALL registered upstream theorems."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.full_lean_plan import build_full_plan,partition_batches


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("mathlib_full_plan.json"))
    p.add_argument("--report",type=Path,default=Path("mathlib_full_plan_report.json"))
    p.add_argument("--batch-limit",type=int,default=60)
    p.add_argument("--worker",type=int)
    p.add_argument("--workers",type=int,default=16)
    a=p.parse_args()
    summary=build_full_plan(a.db,a.output,max_per_batch=a.batch_limit)
    if a.worker is not None:
        plan=json.loads(a.output.read_text(encoding="utf-8"))
        batches=partition_batches(plan,worker=a.worker,workers=a.workers)
        summary["assigned_batches"]=len(batches)
        summary["assigned_declarations"]=sum(
            len(b["registered_declarations"]) for b in batches)
    a.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
