"""Generic, independently checkable MCTS v4 benchmark.

Results measure *engineering cost* on synthetic Horn chains and broad
action spaces, not research-level conjecture performance or new theorems.
All timing assertions are intentionally absent from CI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.incremental_graph import build_incremental_graph
from math_mcts.mcts import Problem, mcts
from math_mcts.reasoning import Atom, Rule, RuleBook, ProofGraph
from math_mcts.hypergraph_closure import forward_certificate


class WideActions(Problem):
    def __init__(self, width: int):
        self.width = width
        self.emitted = 0
        self.eager_generated = 0
    def initial_state(self):
        return "root"
    def actions(self, state):
        if state != "root":
            return []
        self.eager_generated += self.width
        return list(range(self.width))
    def iter_actions(self, state):
        if state != "root":
            return iter(())
        def generate():
            for i in range(self.width):
                self.emitted += 1
                yield i
        return generate()
    def step(self, state, action):
        return ("leaf", action)
    def terminal(self, state):
        return state != "root"
    def reward(self, state):
        return 1.0 if state == ("leaf", 0) else 0.0


def benchmark(*, chain_length: int = 100, width: int = 60000,
              iterations: int = 15, seed: int = 7) -> dict:
    if not all(type(x) is int and x > 0 for x in
               (chain_length, width, iterations)):
        raise ValueError("Benchmark budgets must be positive integers")
    nodes = [Atom(f"s{i}") for i in range(chain_length + 1)]
    rules = [Rule(f"r{i}", (nodes[i],), nodes[i + 1],
                  source="synthetic fixture", status="reviewed")
             for i in range(chain_length)]
    book = RuleBook({x.predicate: () for x in nodes}, {}, rules)
    facts, goal = frozenset([nodes[0]]), nodes[-1]
    started = time.perf_counter()
    original = ProofGraph.build(book, facts, goal, max_rounds=chain_length + 2,
                                max_edges=chain_length + 1, strategy="reference")
    old_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    new, stats = build_incremental_graph(
        book, facts, goal, max_rounds=chain_length + 2,
        max_edges=chain_length + 1, return_stats=True)
    new_ms = (time.perf_counter() - started) * 1000
    equivalent = original.complete and new.complete and set(original.edges) == set(new.edges)
    if not equivalent:
        raise RuntimeError("Grounded inference is not equivalent to the reference")
    proof = forward_certificate(book, new, facts, goal, max_steps=chain_length)
    if proof.certificate is None:
        raise RuntimeError("Closure failed to verify the entire rule chain")
    broad = {}
    for mode in ("eager", "stream"):
        problem = WideActions(width)
        started = time.perf_counter()
        _, root = mcts(problem, action_mode=mode, policy="uct",
                       iterations=iterations, max_depth=1, seed=seed)
        broad[mode] = {
            "search_ms": round((time.perf_counter() - started) * 1000, 4),
            "candidate_actions_materialized": problem.eager_generated,
            "candidate_actions_yielded": problem.emitted,
            "tree_nodes": root.stats["created_nodes"],
            "actual_simulations": root.stats["simulations"],
        }
    return {
        "chain": {"rule_count": chain_length, "exact_edge_sets_equal": equivalent,
                  "proof_replayed": True, "reference_graph_ms": round(old_ms, 4),
                  "delta_graph_ms": round(new_ms, 4),
                  "activated_rule_checks": stats.activated_rule_checks,
                  "avoided_rule_checks": stats.avoided_rule_checks,
                  "duplicate_delta_anchors_skipped": stats.duplicate_delta_anchors_skipped},
        "wide_branching": {"available_actions": width,
                           "iteration_budget": iterations, "methods": broad},
        "proof_scope": "finite reviewed typed positive Horn rules only",
        "claims": "One-run engineering measurement; no mathematical originality, global optimization or universal speedup inferred.",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chain", type=int, default=100)
    p.add_argument("--width", type=int, default=60000)
    p.add_argument("--iterations", type=int, default=15)
    p.add_argument("--output", type=Path, default=Path("mcts_generic_v4_benchmark.json"))
    args = p.parse_args()
    report = benchmark(chain_length=args.chain, width=args.width, iterations=args.iterations)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
