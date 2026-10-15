"""Reproducible generic grounding benchmark (reference vs semi-naive).

Both implementations consume the SAME reviewed RuleBook, assumptions, goal
and budgets. A proof-relevant graph must contain the same exact ground
hyperedges, not merely the same goal-reachable facts. No speedup requirement
is hard-coded: numerical timing depends on the runner and the rule family.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.reasoning import Atom, Rule, RuleBook, ProofGraph, load_reasoning_problem
from math_mcts.incremental_graph import build_incremental_graph
from math_mcts.search_eval import mathematical_task_fixtures


def _chain(depth: int, *, prefix: str = "step"):
    atoms = [Atom(f"{prefix}{i}") for i in range(depth+1)]
    book = RuleBook({a.predicate: () for a in atoms}, {}, [
        Rule(f"rule{i}", (atoms[i],), atoms[i+1],
             source="synthetic benchmark", status="reviewed")
        for i in range(depth)])
    return book, frozenset([atoms[0]]), atoms[-1]


def _breadth(n: int):
    start = Atom("start")
    mid = [Atom(f"mid{i}") for i in range(n)]
    goals = Atom("goal")
    atoms = [start, goals, *mid]
    rules = [Rule(f"begin{i}", (start,), mid[i],
                  source="synthetic benchmark", status="reviewed") for i in range(n)]
    rules.extend(Rule(f"goal{i}", (mid[i],), goals,
                      source="synthetic benchmark", status="reviewed")
                 for i in range(n))
    return RuleBook({a.predicate: () for a in atoms}, {}, rules), frozenset([start]), goals


def benchmark(*, repetitions=3, depth=80, breadth=45) -> dict:
    if not 1 <= repetitions <= 20 or not 1 <= depth <= 500 or not 1 <= breadth <= 300:
        raise ValueError("Invalid benchmark budgets")
    cases = {name: load_reasoning_problem(data)
             for name, data in mathematical_task_fixtures().items()}
    cases["synthetic_deep_chain"] = _chain(depth)
    cases["synthetic_wide_fanout"] = _breadth(breadth)
    results = {}
    for name, (book, assumptions, goal) in sorted(cases.items()):
        max_rounds = max(120, depth + 5)
        times = {"reference": [], "incremental": []}
        graph_reference = None
        graph_incremental = None
        statistics_delta = None
        for _ in range(repetitions):
            start = time.perf_counter()
            graph_reference = ProofGraph.build(book, assumptions, goal,
                                      max_rounds=max_rounds, max_edges=10000,
                                      strategy="reference")
            times["reference"].append((time.perf_counter()-start)*1000)
            start = time.perf_counter()
            graph_incremental, statistics_delta = build_incremental_graph(
                book, assumptions, goal, max_rounds=max_rounds,
                max_edges=10000, return_stats=True)
            times["incremental"].append((time.perf_counter()-start)*1000)
            if (not graph_reference.complete or not graph_incremental.complete
                    or set(graph_reference.edges) != set(graph_incremental.edges)):
                raise RuntimeError("Graph strategies disagree: " + name)
        results[name] = {"ground_edges":len(graph_reference.edges),
                         "reference_ms_median":round(statistics.median(times["reference"]),3),
                         "incremental_ms_median":round(statistics.median(times["incremental"]),3),
                         "delta_premise_match_attempts":statistics_delta.premise_match_attempts,
                         "delta_candidates":statistics_delta.candidate_groundings,
                         "delta_rounds":statistics_delta.rounds,
                         "exact_edge_agreement":True}
    return {"cases":results,"repetitions":repetitions,
            "scope":"generic finite typed reviewed Horn rules",
            "limitations":"Synthetic chain and fanout plus small existing math rules; no guarantee of general faster runtime, no Lean kernel verification or novel theorems."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("grounding_benchmark.json"))
    parser.add_argument("--repetitions",type=int,default=3)
    parser.add_argument("--depth",type=int,default=80)
    parser.add_argument("--breadth",type=int,default=45)
    args=parser.parse_args()
    report=benchmark(repetitions=args.repetitions,depth=args.depth,breadth=args.breadth)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                           encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
