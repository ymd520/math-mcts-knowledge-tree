"""Proof-producing, event-driven reachability in a finite *ground* Horn graph.

It runs in time O(atoms + edges + total premise occurrences), excluding
certificate hashing and verification. This is a least-fixed-point solver
relative to an explicitly reviewed RuleBook, NOT automatic validation of a
natural-language theorem or the source Mathlib declaration.

The first supporting edge yields a sound deterministic witness, but need
not minimize the number of distinct proof steps. A budget failure therefore
means 'not found by this witness', never 'no short proof exists'.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .reasoning import Atom, Certificate, Hyperedge, ProofGraph, RuleBook, _goal_steps, verify_certificate


@dataclass(frozen=True)
class ClosureResult:
    reached: bool
    goal_in_assumptions: bool
    closure_size: int
    scanned_edges: int
    visited_premise_occurrences: int
    attempted_certificate: Certificate | None
    certificate: Certificate | None
    effective_depth: int
    proof_steps: int
    witness_over_budget: bool
    graph_complete: bool
    status: str


def forward_certificate(book: RuleBook, graph: ProofGraph,
                        assumptions: frozenset[Atom], goal: Atom,
                        *, max_steps: int = 10000) -> ClosureResult:
    """Derive a replayable proof of goal from prebuilt ground rules.

    The graph can be incomplete; success is valid if certificate replay succeeds.
    Failure on an incomplete graph is *not* a mathematical disproof.
    State saturation does not honor max_steps: max_steps only limits the final
    returned proof, so a too-long valid witness cannot masquerade as short.
    """
    if max_steps < 0:
        raise ValueError("max_steps must be nonnegative")
    assumptions = frozenset(assumptions)
    for fact in (*assumptions, goal):
        book.validate_atom(fact)
    if goal in assumptions:
        cert = Certificate(goal, assumptions, (), book.fingerprint())
        if not verify_certificate(book, cert, assumptions, goal):
            raise RuntimeError("Initial goal certificate replay failed")
        return ClosureResult(True, True, len(assumptions), 0, 0, cert, cert,
                             0, 0, False, graph.complete, "already_assumed")

    # Preserve graph order for determinism; match edges against the exact
    # reviewed RuleBook so arbitrary or fabricated graph edges cannot be used.
    edges = graph.edges
    dependents: dict[Atom, list[int]] = defaultdict(list)
    remaining = []
    for i, edge in enumerate(edges):
        if book.instantiate(edge.rule_id, dict(edge.binding)) != edge:
            raise ValueError("Ground graph contains an unreviewed or altered edge")
        premises = set(edge.premises)
        remaining.append(len(premises - assumptions))
        for premise in premises:
            dependents[premise].append(i)

    facts = set(assumptions)
    producer: dict[Atom, Hyperedge] = {}
    # Queue zero-premise/initially enabled edges. Process in source order.
    ready = deque(i for i, count in enumerate(remaining) if count == 0)
    visited = 0
    while ready:
        i = ready.popleft()
        edge = edges[i]
        if edge.conclusion in facts:
            continue
        # This invariant matters for zero-premise rules and exact witnesses.
        if not set(edge.premises) <= facts:
            raise RuntimeError("Incorrect Horn event queue")
        facts.add(edge.conclusion)
        producer[edge.conclusion] = edge
        for j in dependents.get(edge.conclusion, ()):
            remaining[j] -= 1
            visited += 1
            if remaining[j] == 0:
                ready.append(j)

    if goal not in facts:
        return ClosureResult(False, False, len(facts), len(edges), visited,
                             None, None, 0, 0, False, graph.complete,
                             "not_derivable_in_graph" if graph.complete
                             else "not_found_in_truncated_graph")

    # Non-recursive DFS avoids recursion depth limits for deep proof chains.
    ordered = []
    visited_atoms = set(assumptions)
    in_progress = set()
    work = [(goal, False)]
    while work:
        atom, finish = work.pop()
        if atom in visited_atoms:
            continue
        if finish:
            in_progress.remove(atom)
            visited_atoms.add(atom)
            ordered.append(producer[atom])
            continue
        if atom in in_progress:
            raise RuntimeError("Cyclic ground proof witness")
        if atom not in producer:
            raise RuntimeError("Missing proof for derived premise")
        in_progress.add(atom)
        work.append((atom, True))
        for parent in reversed(producer[atom].premises):
            if parent not in visited_atoms:
                work.append((parent, False))
    steps, depth = _goal_steps(assumptions, goal, ordered)
    proof = Certificate(goal, assumptions, steps, book.fingerprint())
    if not verify_certificate(book, proof, assumptions, goal):
        raise RuntimeError("Forward proof failed independent replay")
    within = len(steps) <= max_steps
    return ClosureResult(True, False, len(facts), len(edges), visited,
                         proof, proof if within else None, depth,
                         len(steps), not within, graph.complete,
                         "proved_relative_to_reviewed_rules" if within
                         else "valid_witness_exceeds_step_budget")
