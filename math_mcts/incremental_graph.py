"""Semi-naive grounding of reviewed, typed positive Horn rules.

The old graph builder exhaustively rejoined ALL known facts in every round.
This builder only considers substitutions with at least one premise matched
against the *new* fact delta. Other premises match the preceding round's
complete facts, preserving synchronous fixed-point semantics.

The output is a ground ProofGraph relative to the supplied RuleBook. It is
not a source theorem verifier and never enables candidate/refuted rules.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .reasoning import Atom, Hyperedge, ProofGraph, Rule, RuleBook


@dataclass(frozen=True)
class GraphBuildStats:
    rounds: int
    candidate_groundings: int
    unique_edges: int
    known_facts: int
    premise_match_attempts: int
    selected_rules: int
    activated_rule_checks: int
    avoided_rule_checks: int
    duplicate_delta_anchors_skipped: int
    status: str


def _compatible(pattern: Atom, fact: Atom, binding: dict[str, str]):
    if pattern.predicate != fact.predicate or len(pattern.args) != len(fact.args):
        return None
    result = binding.copy()
    for term, actual in zip(pattern.args, fact.args):
        if term.startswith("?"):
            if term in result and result[term] != actual:
                return None
            result[term] = actual
        elif term != actual:
            return None
    return result


def _anchor_bindings(rule: Rule, full: dict[str, list[Atom]],
                     delta: dict[str, list[Atom]], anchor: int, counters: list[int]):
    """Emit typed substitutions without any guesses about missing variables."""
    premises = rule.premises
    # Bind the delta premise first, then join with smallest available buckets.
    others = sorted((i for i in range(len(premises)) if i != anchor),
                    key=lambda i: (len(full.get(premises[i].predicate, ())), i))
    order = [anchor, *others]

    def join(depth: int, current: dict[str, str]):
        if depth == len(order):
            yield current
            return
        index = order[depth]
        pattern = premises[index]
        bucket = delta if index == anchor else full
        for fact in bucket.get(pattern.predicate, ()):
            counters[0] += 1
            updated = _compatible(pattern, fact, current)
            if updated is not None:
                yield from join(depth + 1, updated)

    yield from join(0, {})


def build_incremental_graph(book: RuleBook, assumptions: Iterable[Atom], goal: Atom,
                            *, max_rounds: int = 100, max_edges: int = 10000,
                            return_stats: bool = False):
    """Build a scope-limited ground graph, preserving all positive-Horn edges.

    Completeness is reported only at an actual fixed point. If the edge or
    round budget is exhausted, the graph is marked incomplete. No proof of
    nonderivability can be inferred from an incomplete graph.

    This implementation is monotone and delta-based, not globally linear:
    joins with many variable combinations may still be exponentially large.
    """
    if type(max_rounds) is not int or type(max_edges) is not int or max_rounds < 1 or max_edges < 1:
        raise ValueError("Positive integer graph budgets required")
    assumptions = frozenset(assumptions)
    for atom in (*assumptions, goal):
        book.validate_atom(atom)
    rules = book.backward_rules(goal)  # reviewed rules only
    # Index *premise predicate -> eligible rules* once. Unrelated rules
    # are never revisited on rounds where no matching predicate changed.
    rule_by_predicate: dict[str, set[int]] = defaultdict(set)
    premise_free: set[int] = set()
    for ri, rule in enumerate(rules):
        if not rule.premises:
            premise_free.add(ri)
        for premise in rule.premises:
            rule_by_predicate[premise.predicate].add(ri)
    facts = set(assumptions)
    delta = set(assumptions)
    full_index: dict[str, list[Atom]] = defaultdict(list)
    for fact in sorted(facts):
        full_index[fact.predicate].append(fact)
    edges: dict[Hyperedge, None] = {}
    counters = [0]
    candidates = 0
    rounds = 0
    activated_checks = 0
    avoided_checks = 0
    duplicate_anchors = 0

    def finish(complete: bool, reason: str):
        graph = ProofGraph(tuple(edges), complete, reason)
        stats = GraphBuildStats(rounds, candidates, len(edges), len(facts),
                                counters[0], len(rules),
                                activated_checks, avoided_checks,
                                duplicate_anchors, "ground_reviewed_rules_only")
        return (graph, stats) if return_stats else graph

    for round_index in range(max_rounds):
        rounds += 1
        delta_index: dict[str, list[Atom]] = defaultdict(list)
        for fact in sorted(delta):
            delta_index[fact.predicate].append(fact)
        new_facts: set[Atom] = set()
        active = set(premise_free) if round_index == 0 else set()
        for predicate in delta_index:
            active.update(rule_by_predicate.get(predicate, ()))
        activated_checks += len(active)
        avoided_checks += len(rules) - len(active)
        for ri in sorted(active):
            rule = rules[ri]
            if not rule.premises:
                bindings = ({},) if round_index == 0 else ()
                for binding in bindings:
                    candidates += 1
                    edge = book.instantiate(rule.id, binding)
                    if edge not in edges:
                        if len(edges) >= max_edges:
                            return finish(False, "edge_budget")
                        edges[edge] = None
                    if edge.conclusion not in facts:
                        new_facts.add(edge.conclusion)
                continue

            # Every newly enabled rule instance has at least one matching
            # premise in the preceding round's delta. Instances matching
            # several positions may be enumerated twice, but deduplicated.
            for anchor in range(len(rule.premises)):
                if not delta_index.get(rule.premises[anchor].predicate):
                    continue
                for binding in _anchor_bindings(rule, full_index, delta_index,
                                                anchor, counters):
                    # A rule instance whose several premises are new this
                    # round belongs to its FIRST matching delta anchor.
                    # This avoids redundant candidate instantiations.
                    if any(rule.premises[j].instantiate(binding) in delta
                           for j in range(anchor)):
                        duplicate_anchors += 1
                        continue
                    candidates += 1
                    edge = book.instantiate(rule.id, binding)
                    if edge not in edges:
                        if len(edges) >= max_edges:
                            return finish(False, "edge_budget")
                        edges[edge] = None
                    if edge.conclusion not in facts:
                        new_facts.add(edge.conclusion)
        if not new_facts:
            return finish(True, "fixed_point")
        delta = new_facts - facts
        facts.update(delta)
        for fact in sorted(delta):
            full_index[fact.predicate].append(fact)
    return finish(False, "round_budget")
