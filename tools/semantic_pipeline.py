"""Build source-bound typed graph and run certificate-checked math tasks.

Generate graph from a user-supplied JSON with *reviewed* typed Horn rules.
Unreviewed catalog source statements are never translated or promoted here.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from math_mcts.reasoning import load_reasoning_problem
from math_mcts.semantic_graph import build_semantic_graph,SemanticGraph
from math_mcts.search_eval import benchmark_suite,mathematical_task_fixtures


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--problem",type=Path,help="Typed reviewed Horn problem JSON")
    p.add_argument("--graph",type=Path,default=Path("semantic_rules.sqlite"))
    p.add_argument("--benchmark",action="store_true")
    p.add_argument("--iterations",type=int,default=200)
    p.add_argument("--max-steps",type=int,default=16)
    p.add_argument("--beam-width",type=int,default=12)
    p.add_argument("--output",type=Path,default=Path("semantic_benchmark.json"))
    args=p.parse_args()
    if args.benchmark:
        result=benchmark_suite(mathematical_task_fixtures(),
              iterations=args.iterations,max_steps=args.max_steps,
              beam_width=args.beam_width)
    elif args.problem:
        payload=json.loads(args.problem.read_text(encoding="utf-8"))
        book,_,goal=load_reasoning_problem(payload)
        result=build_semantic_graph(book,args.graph)
        result["goal_relevant_rules"]=SemanticGraph(
            args.graph,book=book).backward_relevant_rules(book,goal.predicate)
    else:
        p.error("specify --problem or --benchmark")
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,
                                       sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":
    main()
