"""Typed mathematical rule-composition candidates (not proofs).

Unlike tag-based concept collisions, these candidates are screened for an
actual producer-conclusion / consumer-premise unifier, with equality and sort
constraints inherited from RuleBook. Additional premises remain explicit.
"""
from __future__ import annotations
from collections import defaultdict


def _term(side: str, token: str) -> str:
    return side + ":" + token if token.startswith("?") else "constant:" + token


def compatible_atoms(producer, consumer) -> bool:
    if producer.predicate != consumer.predicate or len(producer.args) != len(consumer.args):
        return False
    parents = {}
    constants = {}
    def find(x):
        parents.setdefault(x, x)
        if parents[x] != x:
            parents[x] = find(parents[x])
        return parents[x]
    def union(x, y):
        a, b = find(x), find(y)
        if a == b:
            return True
        ca = constants.get(a)
        cb = constants.get(b)
        if ca is not None and cb is not None and ca != cb:
            return False
        parents[b] = a
        if ca is not None or cb is not None:
            constants[a] = ca if ca is not None else cb
        return True
    for u, v in zip(producer.args, consumer.args):
        a, b = _term("producer", u), _term("consumer", v)
        if a.startswith("constant:"):
            constants[find(a)] = u
        if b.startswith("constant:"):
            constants[find(b)] = v
        if not union(a, b):
            return False
    return True


def find_composable_rules(book, *, limit: int = 100,
                          goal_predicate: str | None = None) -> list[dict]:
    """O(rules + indexed premise candidates), goal-filtered composability.

    This does not assert existence of a proof or solvability of remaining
    premises. It produces a constrained graph for subsequent MCTS scheduling.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    consumer_index = defaultdict(list)
    for rule in book.rules.values():
        for index, atom in enumerate(rule.premises):
            consumer_index[atom.predicate].append((rule, index, atom))
    found = []
    for producer in sorted(book.rules.values(), key=lambda r: r.id):
        if goal_predicate and producer.conclusion.predicate != goal_predicate:
            continue
        for consumer, index, premise in consumer_index.get(producer.conclusion.predicate, ()):
            if consumer.id == producer.id:
                continue
            if not compatible_atoms(producer.conclusion, premise):
                continue
            required = [p.predicate for p in producer.premises]
            required += [p.predicate for i, p in enumerate(consumer.premises) if i != index]
            found.append({
                "producer": producer.id,
                "consumer": consumer.id,
                "bridge_predicate": producer.conclusion.predicate,
                "consumer_premise_index": index,
                "remaining_premise_predicates": required,
                "status": "typed_composition_candidate_not_a_proof",
            })
            if len(found) >= limit:
                return found
    return found
