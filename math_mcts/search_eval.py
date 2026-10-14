"""Budgeted baselines and test scenarios for typed mathematical derivation.

These are concrete elementary-math reasoning tasks, grounded in explicit
reviewed rules and assumptions. Successful certificates prove derivability
*relative to those rules*, not novel theorems or external correctness of mathlib.
All solvers share a single, up-front candidate hypergraph.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
import json
import time
from pathlib import Path

from .mcts import mcts
from .reasoning import (Atom, RuleBook, Certificate, DerivationProblem,
                        ProofGraph, ProofState, _goal_steps, verify_certificate,
                        load_reasoning_problem)


@dataclass
class BaselineResult:
    method: str
    solved: bool
    certificate: Certificate | None
    states_expanded: int
    generated_states: int
    elapsed_ms: float
    effective_depth: int
    valid_replay: bool
    scope_complete: bool


def _certificate(book, assumptions, goal, state):
    if state is None or goal not in state.facts:
        return None, 0, False
    steps, depth = _goal_steps(assumptions, goal, state.steps)
    cert = Certificate(goal, assumptions, steps, book.fingerprint())
    return cert, depth, verify_certificate(book, cert, assumptions, goal)


def solve_baseline(book: RuleBook, assumptions, goal: Atom, *,
                   method: str = "bfs", max_expansions: int = 200,
                   max_steps: int = 16, beam_width: int = 12,
                   graph: ProofGraph | None = None) -> BaselineResult:
    if method not in {"bfs", "beam"}:
        raise ValueError("method must be bfs/beam")
    if max_expansions < 1 or max_steps < 1 or beam_width < 1:
        raise ValueError("positive budgets required")
    start = time.perf_counter()
    assumptions = frozenset(assumptions)
    graph = graph or ProofGraph.build(book, assumptions, goal)
    problem = DerivationProblem(graph, assumptions, goal, max_steps)
    initial = problem.initial_state()
    frontier = deque([initial])
    seen = {initial.facts}
    explored, generated = 0, 1
    best = initial if goal in initial.facts else None
    # Relevance heuristic is predicate-level, not an assertion of truth.
    relevant = {goal.predicate}
    for r in book.backward_rules(goal):
        relevant.add(r.conclusion.predicate)
        relevant.update(p.predicate for p in r.premises)
    while frontier and explored < max_expansions and best is None:
        if method == "bfs":
            state = frontier.popleft()
        else:
            state = frontier.popleft()  # sort/limit at each wave below
        explored += 1
        choices = problem.actions(state)
        for action in choices:
            child = problem.step(state, action)
            if child.facts in seen:
                continue
            seen.add(child.facts)
            generated += 1
            if goal in child.facts:
                best = child
                break
            frontier.append(child)
        if method == "beam" and frontier:
            # An intentionally bounded, deterministic, goal-relevance beam;
            # not a claim of optimality or completeness.
            ranked = sorted(frontier,
                            key=lambda s: (-sum(a.predicate in relevant for a in s.facts),
                                           len(s.steps),
                                           tuple(sorted((a.predicate, a.args) for a in s.facts))))
            frontier = deque(ranked[:beam_width])
    cert, depth, replay = _certificate(book, assumptions, goal, best)
    return BaselineResult(method, cert is not None and replay, cert,
                          explored, generated, (time.perf_counter()-start)*1000,
                          depth, replay, graph.complete)


def benchmark_rule_problem(data: dict, *, iterations: int = 200,
                           max_steps: int = 16, beam_width: int = 12,
                           seed: int = 7) -> dict:
    book, assumptions, goal = load_reasoning_problem(data)
    started = time.perf_counter()
    graph = ProofGraph.build(book, assumptions, goal, max_edges=3000, max_rounds=40)
    graph_ms = (time.perf_counter() - started) * 1000
    results = []
    for method in ("bfs", "beam"):
        outcome = solve_baseline(book, assumptions, goal, graph=graph,
                                 method=method, max_steps=max_steps,
                                 max_expansions=iterations, beam_width=beam_width)
        results.append({"method": method, "solved": outcome.solved,
                        "states_expanded": outcome.states_expanded,
                        "generated_states": outcome.generated_states,
                        "search_elapsed_ms": round(outcome.elapsed_ms, 3),
                        "effective_depth": outcome.effective_depth,
                        "certificate_replayed": outcome.valid_replay})
    # Evaluate MCTS on precisely the same prebuilt hypergraph.
    # This avoids incorrectly charging only MCTS for graph construction.
    mc_problem = DerivationProblem(graph, assumptions, goal, max_steps)
    started = time.perf_counter()
    _, mc_root = mcts(mc_problem, iterations=iterations, max_depth=max_steps,
                      seed=seed)
    elapsed = (time.perf_counter()-started)*1000
    mc_cert, mc_depth, mc_replay = _certificate(
        book, assumptions, goal, mc_problem.best)
    if mc_cert is not None and not mc_replay:
        raise RuntimeError("MCTS certificate failed independent replay")
    active = [mc_root]
    tree_nodes = 0
    while active:
        cur = active.pop()
        tree_nodes += 1
        active.extend(cur.children)
    results.append({"method": "mcts", "solved": mc_cert is not None,
                    "states_expanded": None, "iterations": iterations,
                    "generated_states": tree_nodes,
                    "search_elapsed_ms": round(elapsed,3),
                    "effective_depth": mc_depth,
                    "certificate_replayed": mc_replay,
                    "scope_complete": graph.complete})
    return {"graph_edges": len(graph.edges), "graph_complete": graph.complete,
            "graph_reason": graph.reason,
            "graph_construction_ms": round(graph_ms,3), "methods": results,
            "limitations": ("All solvers share one prebuilt hypergraph, and per-solver "
                            "timing excludes graph creation. MCTS iterations differ "
                            "from BFS/beam state expansions; this benchmark reports "
                            "observed costs and proof success, not equal-work speedups.")}


def benchmark_suite(problems: dict[str,dict], *, iterations=200,
                    max_steps=16, beam_width=12, seed=7):
    return {
        "scenarios": {name: benchmark_rule_problem(problem, iterations=iterations,
                      max_steps=max_steps, beam_width=beam_width, seed=seed)
                      for name,problem in sorted(problems.items())},
        "status": "observed_bounded_search_not_global_optimality_or_new_theorems",
    }


def mathematical_task_fixtures() -> dict[str, dict]:
    """Elementary valid implications: explicit sorts and manually listed facts."""
    def a(predicate, *args):
        return {"predicate": predicate, "args": list(args)}
    def rule(ident, premises, conclusion, variables, source):
        return {"id": ident, "premises": premises, "conclusion": conclusion,
                "variables": variables, "source": source, "status": "reviewed"}
    return {
        "divisibility_transitivity": {
            "signatures": {"divides": ["Nat","Nat"]},
            "objects": {"2":"Nat","4":"Nat","8":"Nat","16":"Nat"},
            "assumptions": [a("divides","2","4"),a("divides","4","8"),
                            a("divides","8","16")],
            "goal": a("divides","2","16"),
            "rules": [rule("div_trans",
                [a("divides","?a","?b"),a("divides","?b","?c")],
                a("divides","?a","?c"),
                {"?a":"Nat","?b":"Nat","?c":"Nat"},
                "elementary divisibility transitivity")],
        },
        "subset_transitivity": {
            "signatures": {"subset":["Set","Set"]},
            "objects":{"A":"Set","B":"Set","C":"Set","D":"Set"},
            "assumptions":[a("subset","A","B"),a("subset","B","C"),
                           a("subset","C","D")],
            "goal":a("subset","A","D"),
            "rules":[rule("subset_trans",
                [a("subset","?a","?b"),a("subset","?b","?c")],
                a("subset","?a","?c"),
                {"?a":"Set","?b":"Set","?c":"Set"},
                "elementary inclusion transitivity")],
        },
        "membership_transport": {
            "signatures":{"member":["Elem","Set"],"subset":["Set","Set"]},
            "objects":{"x":"Elem","A":"Set","B":"Set","C":"Set","D":"Set"},
            "assumptions":[a("member","x","A"),a("subset","A","B"),
                           a("subset","B","C"),a("subset","C","D")],
            "goal":a("member","x","D"),
            "rules":[rule("member_sub",
                [a("member","?x","?a"),a("subset","?a","?b")],
                a("member","?x","?b"),
                {"?x":"Elem","?a":"Set","?b":"Set"},
                "elementary subset element transport")],
        },
    }
