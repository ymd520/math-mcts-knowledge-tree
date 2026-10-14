"""Reproducible, equal-budget comparison of closure, UCT and guided PUCT.

All three use the SAME precomputed reviewed-rule ground hypergraph.
Wall-clock time includes only each search, not graph construction.
MCTS simulations and deterministic closure edge processing are NOT equal units
of work; this script reports observations, not a guaranteed speedup.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.hypergraph_closure import forward_certificate
from math_mcts.mcts import mcts
from math_mcts.reasoning import DerivationProblem, ProofGraph, load_reasoning_problem
from math_mcts.search_eval import _certificate, mathematical_task_fixtures


def evaluate(*, iterations=180, max_steps=18, seed=7) -> dict:
    if iterations < 1 or max_steps < 1:
        raise ValueError("Positive benchmark budgets required")
    cases = {}
    for name, spec in sorted(mathematical_task_fixtures().items()):
        book, assumptions, goal = load_reasoning_problem(spec)
        beginning = time.perf_counter()
        graph = ProofGraph.build(book, assumptions, goal)
        construction_ms = (time.perf_counter() - beginning) * 1000
        rows = []
        start = time.perf_counter()
        proof = forward_certificate(book, graph, assumptions, goal, max_steps=max_steps)
        rows.append({"method": "event_driven_closure", "solved": proof.certificate is not None,
                     "certificate_replayed": proof.certificate is not None,
                     "search_elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                     "scanned_ground_edges": proof.scanned_edges,
                     "visited_premise_occurrences": proof.visited_premise_occurrences,
                     "proof_steps": proof.proof_steps,
                     "status": proof.status})
        for policy, stop in (("uct", False), ("puct", True)):
            problem = DerivationProblem(graph, assumptions, goal, max_steps)
            start = time.perf_counter()
            _, root = mcts(problem, iterations=iterations, max_depth=max_steps,
                           seed=seed, policy=policy, stop_on_success=stop)
            elapsed = (time.perf_counter() - start) * 1000
            cert, depth, replayed = _certificate(book, assumptions, goal, problem.best)
            if cert is not None and not replayed:
                raise RuntimeError("MCTS produced an invalid certificate")
            rows.append({"method": "guided_puct" if policy == "puct" else "plain_uct",
                         "solved": cert is not None and replayed,
                         "certificate_replayed": replayed,
                         "search_elapsed_ms": round(elapsed, 3),
                         "requested_iterations": iterations,
                         "actual_simulations": root.stats["simulations"],
                         "created_tree_nodes": root.stats["created_nodes"],
                         "early_stop": root.stats["early_stop"],
                         "effective_proof_depth": depth})
        cases[name] = {"graph_edges": len(graph.edges),
                       "graph_complete": graph.complete,
                       "graph_construction_ms": round(construction_ms, 3),
                       "results": rows}
    return {"cases": cases, "budget_simulations_per_mcts": iterations,
            "scope": "finite_ground_reviewed_horn_rules_only",
            "limitations": "Graph construction excluded equally; MCTS and closure workloads are not directly comparable. Individual timings are environment-sensitive. No new mathematics or universal acceleration is claimed."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("mcts_v2_benchmark.json"))
    p.add_argument("--iterations", type=int, default=180)
    p.add_argument("--max-steps", type=int, default=18)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    result = evaluate(iterations=args.iterations, max_steps=args.max_steps, seed=args.seed)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
