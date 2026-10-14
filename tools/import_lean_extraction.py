"""Import extracted Lean environment references into a provenance-locked DB.

Important: merely submitting JSON cannot establish Lean kernel execution.
The main CI tests strict source matching, graph traversal and stale-input
rejection; a separate Lean CI job runs an actual elaboration smoke test.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from math_mcts.lean_reference_index import (import_lean_exports,
                                            LeanReferenceGraph)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--jsonl",type=Path,help="JSONL emitted from pinned Lean environment")
    p.add_argument("--report",type=Path,default=Path("lean_reference_report.json"))
    p.add_argument("--inspect",help="Registered ID to inspect")
    p.add_argument("--max-hops",type=int,default=3)
    a=p.parse_args()
    if a.inspect:
        result=LeanReferenceGraph(a.db).backward_dependencies(
            a.inspect,max_hops=a.max_hops)
    elif a.jsonl:
        result=import_lean_exports(a.db,a.jsonl)
        a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)
                            +"\n",encoding="utf-8")
    else:
        p.error("Provide --jsonl or --inspect")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
