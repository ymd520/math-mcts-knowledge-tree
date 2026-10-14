"""Source-checked indexing of elaborated Lean binder domains and goals."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.lean_type_semantics import (
    index_elaborated_type_structure,candidate_type_connections)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--exports",required=True,type=Path)
    p.add_argument("--report",type=Path,default=Path("lean_type_semantics_report.json"))
    p.add_argument("--candidates-output",type=Path,
                   default=Path("lean_typed_link_candidates.json"))
    p.add_argument("--candidate-limit",type=int,default=100)
    a=p.parse_args()
    report=index_elaborated_type_structure(a.db,a.exports)
    candidates=candidate_type_connections(a.db,limit=a.candidate_limit)
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    a.candidates_output.write_text(
        json.dumps({"candidate_count":len(candidates),"proofs":0,
                    "matching_scope":"identical_Lean_AST_candidates_only",
                    "connections":candidates},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
