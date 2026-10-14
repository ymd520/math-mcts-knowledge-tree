"""Fail-closed search routing among BFS, beam and MCTS.

A search policy is a budgeted heuristic, not a theorem about optimality. Every
successful result is replayed against the SAME source-bound RuleBook. Standard
benchmark tasks are kept separate from stress/holdout graphs.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import time

from .mcts import mcts
from .reasoning import ProofGraph, DerivationProblem
from .search_eval import _certificate, solve_baseline


def choose_search_method(graph: ProofGraph, initial_actions: int,
                         *, exact_edge_threshold: int=120,
                         wide_frontier: int=16) -> tuple[str, dict]:
    if exact_edge_threshold<1 or wide_frontier<1:
        raise ValueError("Invalid routing threshold")
    if not graph.complete:
        # An incomplete graph must never claim an exhaustive search result.
        return "beam", {"reason":"incomplete_precomputed_graph",
                        "completeness":"not_guaranteed"}
    if len(graph.edges)<=exact_edge_threshold:
        return "bfs", {"reason":"small_complete_graph"}
    if initial_actions<wide_frontier:
        return "beam", {"reason":"large_graph_narrow_initial_frontier"}
    return "mcts", {"reason":"large_complete_graph_wide_frontier",
                    "warning":"no guaranteed speedup over BFS or beam"}


def solve_adaptive(book, assumptions, goal, *, max_steps=20,
                   iterations=400, seed=7, edge_limit=3000,
                   round_limit=60, beam_width=16,
                   exact_edge_threshold=120,
                   wide_frontier=16):
    if iterations<1:
        raise ValueError("iterations must be positive")
    graph=ProofGraph.build(book,frozenset(assumptions),goal,
                           max_rounds=round_limit,max_edges=edge_limit)
    problem=DerivationProblem(graph,frozenset(assumptions),goal,max_steps)
    method,selection=choose_search_method(
        graph,len(problem.actions(problem.initial_state())),
        exact_edge_threshold=exact_edge_threshold,wide_frontier=wide_frontier)
    if method!="mcts":
        result=solve_baseline(book,assumptions,goal,graph=graph,method=method,
                              max_steps=max_steps,max_expansions=iterations,
                              beam_width=beam_width)
        return {"method":method,"route":selection,"solved":result.solved,
                "replayed":result.valid_replay,
                "depth":result.effective_depth,
                "graph_complete":graph.complete,
                "graph_size":len(graph.edges),
                "states_expanded":result.states_expanded,
                "search_elapsed_ms":result.elapsed_ms}
    started=time.perf_counter()
    _,root=mcts(problem,iterations=iterations,max_depth=max_steps,seed=seed)
    certificate,depth,replayed=_certificate(
        book,frozenset(assumptions),goal,problem.best)
    if certificate is not None and not replayed:
        raise RuntimeError("MCTS certificate failed independent replay")
    return {"method":"mcts","route":selection,
            "solved":certificate is not None,"replayed":replayed,
            "depth":depth,"graph_complete":graph.complete,
            "graph_size":len(graph.edges),
            "iterations":iterations,
            "search_elapsed_ms":(time.perf_counter()-started)*1000}
