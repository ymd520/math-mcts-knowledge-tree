"""Exact pinned-source file authorship index for all registered theorems."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.mathlib_credit_index import index_module_authors


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--mathlib-root",type=Path,required=True)
    p.add_argument("--report",type=Path,default=Path("all_mathlib_source_credits.json"))
    a=p.parse_args()
    report=index_module_authors(a.db,a.mathlib_root)
    a.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
