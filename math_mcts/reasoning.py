"""Typed, function-free Horn reasoning; MCTS schedules legal hyperedges.

Certificates establish derivability relative to caller-supplied assumptions and
reviewed rules, NOT theorem truth, novelty, or Lean kernel verification.
Variables are ?name, constants have explicit sorts. No negation, quantifiers,
equality rewriting or automatic parsing of natural-language/Lean statements.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from collections import Counter, OrderedDict
import hashlib
import json
from typing import Mapping

from .mcts import Problem, mcts


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    args: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "args", tuple(self.args))
        if not self.predicate or any(not isinstance(a, str) or not a for a in self.args):
            raise ValueError("Atoms require a predicate and nonempty string terms")

    def instantiate(self, binding: Mapping[str, str]) -> "Atom":
        return Atom(self.predicate, tuple(binding.get(a, a) for a in self.args))


@dataclass(frozen=True)
class Rule:
    id: str
    premises: tuple[Atom, ...]
    conclusion: Atom
    variables: tuple[tuple[str, str], ...] = ()
    source: str = ""
    status: str = "candidate"
    # Explicit knowledge provenance participates in RuleBook.fingerprint().
    # Legacy stand-alone rules may leave these fields empty.
    concept_id: str = ""
    concept_sha256: str = ""
    mapping_review: str = ""

    def __post_init__(self):
        object.__setattr__(self, "premises", tuple(self.premises))
        object.__setattr__(self, "variables", tuple(tuple(v) for v in self.variables))


@dataclass(frozen=True)
class Hyperedge:
    rule_id: str
    binding: tuple[tuple[str, str], ...]
    premises: tuple[Atom, ...]
    conclusion: Atom


@dataclass(frozen=True)
class Certificate:
    goal: Atom
    assumptions: frozenset[Atom]
    steps: tuple[Hyperedge, ...]
    rulebook_sha256: str = ""


@dataclass
class SearchResult:
    status: str
    certificate: Certificate | None
    effective_depth: int
    applied_rules: int
    iterations: int
    generated_edges: int
    scope_complete: bool
    scope_reason: str


class RuleBook:
    """Explicit trusted boundary: reviewed rules + fixed typed object universe."""

    def __init__(self, signatures: Mapping[str, tuple[str, ...]],
                 objects: Mapping[str, str], rules: list[Rule]):
        self.signatures = {k: tuple(v) for k, v in signatures.items()}
        self.objects = dict(objects)
        if any(not k or k.startswith("?") or not v for k, v in self.objects.items()):
            raise ValueError("Invalid constant/sort")
        self.rules: dict[str, Rule] = {}
        self.candidates: dict[str, Rule] = {}
        for rule in rules:
            if not rule.id or rule.id in self.rules or rule.id in self.candidates:
                raise ValueError("Duplicate or empty rule id")
            variables = dict(rule.variables)
            if len(variables) != len(rule.variables) or any(
                    not k.startswith("?") or not v for k, v in variables.items()):
                raise ValueError("Invalid variable declaration")
            for atom in (*rule.premises, rule.conclusion):
                self.validate_atom(atom, variables)
            # No invented witnesses: every variable must be bound by premises.
            bound = {a for p in rule.premises for a in p.args if a.startswith("?")}
            if set(variables) != bound:
                raise ValueError("All variables must occur in premises")
            if rule.status == "reviewed":
                if rule.concept_id and not (rule.concept_sha256 and rule.mapping_review):
                    raise ValueError("Mapped reviewed rule requires concept snapshot and review")
                if not rule.source:
                    raise ValueError("Reviewed rule requires provenance")
                self.rules[rule.id] = rule
            elif rule.status in {"candidate", "refuted"}:
                self.candidates[rule.id] = rule
            else:
                raise ValueError("Unknown rule status")

    def validate_atom(self, atom: Atom, variables=None):
        signature = self.signatures.get(atom.predicate)
        if signature is None or len(signature) != len(atom.args):
            raise ValueError("Unknown predicate or wrong arity")
        variables = variables or {}
        for term, sort in zip(atom.args, signature):
            actual = variables.get(term) if term.startswith("?") else self.objects.get(term)
            if actual != sort:
                raise ValueError(f"Type mismatch: {term} needs {sort}")

    def instantiate(self, rule_id: str, binding: Mapping[str, str]) -> Hyperedge:
        rule = self.rules[rule_id]
        variables = dict(rule.variables)
        if set(binding) != set(variables):
            raise ValueError("Incomplete or extra substitution")
        if any(self.objects.get(binding[v]) != sort for v, sort in variables.items()):
            raise ValueError("Ill-typed substitution")
        return Hyperedge(rule.id, tuple(sorted(binding.items())),
                         tuple(p.instantiate(binding) for p in rule.premises),
                         rule.conclusion.instantiate(binding))

    def fingerprint(self):
        payload = {"signatures": self.signatures, "objects": self.objects,
                   "rules": [asdict(self.rules[k]) for k in sorted(self.rules)]}
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                        ensure_ascii=False).encode()).hexdigest()

    def matches(self, rule: Rule, facts: frozenset[Atom], *, fact_index=None):
        """Join all premises, preserving repeated-variable equality."""
        index = fact_index
        if index is None:
            index = {}
            for atom in sorted(facts):
                index.setdefault(atom.predicate, []).append(atom)
        def join(position, binding):
            if position == len(rule.premises):
                yield binding
                return
            pattern = rule.premises[position]
            for fact in index.get(pattern.predicate, ()):
                new = dict(binding)
                for term, actual in zip(pattern.args, fact.args):
                    if term.startswith("?"):
                        if term in new and new[term] != actual:
                            break
                        new[term] = actual
                    elif term != actual:
                        break
                else:
                    yield from join(position + 1, new)
        for binding in join(0, {}):
            yield self.instantiate(rule.id, binding)

    def backward_rules(self, goal: Atom) -> tuple[Rule, ...]:
        """Conservative predicate-level relevance, not a complete backward prover."""
        needed = {goal.predicate}
        selected = {}
        while True:
            before = len(selected)
            for rule in self.rules.values():
                if rule.conclusion.predicate in needed:
                    selected[rule.id] = rule
                    needed.update(p.predicate for p in rule.premises)
            if len(selected) == before:
                return tuple(selected[k] for k in sorted(selected))


@dataclass
class ProofGraph:
    edges: tuple[Hyperedge, ...]
    complete: bool
    reason: str

    @classmethod
    def build(cls, book: RuleBook, assumptions: frozenset[Atom], goal: Atom,
              max_rounds: int = 100, max_edges: int = 10000) -> "ProofGraph":
        if max_rounds < 1 or max_edges < 1:
            raise ValueError("Positive graph budgets required")
        for atom in (*assumptions, goal):
            book.validate_atom(atom)
        facts = assumptions
        edges = {}
        rules = book.backward_rules(goal)
        for _ in range(max_rounds):
            new = set(facts)
            for rule in rules:
                for edge in book.matches(rule, facts):
                    if edge not in edges:
                        if len(edges) >= max_edges:
                            return cls(tuple(edges), False, "edge_budget")
                        edges[edge] = None
                    new.add(edge.conclusion)
            if new == set(facts):
                return cls(tuple(edges), True, "fixed_point")
            facts = frozenset(new)
        return cls(tuple(edges), False, "round_budget")


def verify_certificate(book: RuleBook, certificate: Certificate,
                       expected_assumptions: frozenset[Atom], expected_goal: Atom) -> bool:
    """Replay each edge; reject added assumptions and tampered rules/bindings."""
    if certificate.assumptions != expected_assumptions or certificate.goal != expected_goal:
        return False
    if certificate.rulebook_sha256 != book.fingerprint():
        return False
    try:
        for atom in (*certificate.assumptions, certificate.goal):
            book.validate_atom(atom)
        facts = set(certificate.assumptions)
        for edge in certificate.steps:
            actual = book.instantiate(edge.rule_id, dict(edge.binding))
            if actual != edge or not set(edge.premises) <= facts or edge.conclusion in facts:
                return False
            facts.add(edge.conclusion)
        return certificate.goal in facts
    except (KeyError, ValueError, TypeError):
        return False


@dataclass(frozen=True)
class ProofState:
    facts: frozenset[Atom]
    steps: tuple[Hyperedge, ...] = ()


class DerivationProblem(Problem):
    """MCTS chooses enabled multi-premise edges, never assumes missing premises."""

    def __init__(self, graph: ProofGraph, assumptions: frozenset[Atom],
                 goal: Atom, max_steps: int):
        self.graph, self.assumptions, self.goal = graph, assumptions, goal
        self.max_steps = max_steps
        self.best: ProofState | None = None
        # Share enabled-edge computations across equivalent fact states.
        # Search-tree visit statistics remain per path (no unsound DAG UCT reuse).
        self._actions = OrderedDict()
        self._cache_capacity = 4096
        # Each hyperedge is indexed by *one* required premise (the rarest
        # ground atom among edges); only facts present in the current state
        # can enable that edge. Ground, premise-free rules remain globally
        # eligible. This preserves exact enabled-action semantics.
        frequency = Counter(
            atom for edge in graph.edges for atom in set(edge.premises))
        self._indexed_edges = {}
        self._empty_premise_edges = []
        for i, edge in enumerate(graph.edges):
            if not edge.premises:
                self._empty_premise_edges.append((i, edge))
                continue
            anchor = min(set(edge.premises),
                         key=lambda atom: (frequency[atom], atom))
            self._indexed_edges.setdefault(anchor, []).append((i, edge))

    def initial_state(self):
        return ProofState(self.assumptions)

    def actions(self, state):
        if self.goal in state.facts or len(state.steps) >= self.max_steps:
            return []
        if state.facts in self._actions:
            self._actions.move_to_end(state.facts)
            return list(self._actions[state.facts])
        possible = list(self._empty_premise_edges)
        for fact in state.facts:
            possible.extend(self._indexed_edges.get(fact, ()))
        possible.sort(key=lambda pair: pair[0])
        enabled = tuple(
            edge for _, edge in possible
            if edge.conclusion not in state.facts
            and set(edge.premises) <= state.facts)
        self._actions[state.facts] = enabled
        self._actions.move_to_end(state.facts)
        if len(self._actions) > self._cache_capacity:
            self._actions.popitem(last=False)
        return list(enabled)

    def step(self, state, action):
        if action not in self.actions(state):
            raise ValueError("Disabled inference")
        return ProofState(state.facts | {action.conclusion}, state.steps + (action,))

    def terminal(self, state):
        return not self.actions(state)

    def reward(self, state):
        if self.goal in state.facts:
            if self.best is None or len(state.steps) < len(self.best.steps):
                self.best = state
            return 1.0
        # No reward for unproved guesses or mere chain length.
        return 0.0


def _goal_steps(assumptions, goal, steps):
    """Keep only the goal dependency cone; compute longest dependency depth."""
    producer = {edge.conclusion: edge for edge in steps}
    needed = set()
    depths = {atom: 0 for atom in assumptions}

    def visit(atom):
        if atom in depths:
            return depths[atom]
        edge = producer[atom]
        needed.add(edge)
        depths[atom] = 1 + max((visit(p) for p in edge.premises), default=0)
        return depths[atom]

    depth = visit(goal)
    return tuple(e for e in steps if e in needed), depth


def derive(book: RuleBook, assumptions, goal: Atom, *, iterations: int = 1000,
           max_steps: int = 50, seed: int = 7, max_rounds: int = 100,
           max_edges: int = 10000) -> SearchResult:
    """Bounded proof scheduling over an explicitly reviewed Horn rule scope."""
    if iterations < 1 or max_steps < 1:
        raise ValueError("Positive search budgets required")
    assumptions = frozenset(assumptions)
    graph = ProofGraph.build(book, assumptions, goal, max_rounds, max_edges)
    problem = DerivationProblem(graph, assumptions, goal, max_steps)
    mcts(problem, iterations=iterations, max_depth=max_steps, seed=seed)
    if problem.best is None:
        return SearchResult("not_found_within_budget", None, 0, 0, iterations,
                            len(graph.edges), graph.complete, graph.reason)
    steps, depth = _goal_steps(assumptions, goal, problem.best.steps)
    cert = Certificate(goal, assumptions, steps, book.fingerprint())
    if not verify_certificate(book, cert, assumptions, goal):
        raise RuntimeError("Internal certificate replay failed")
    return SearchResult("derived_relative_to_rules", cert, depth, len(steps),
                        iterations, len(graph.edges), graph.complete, graph.reason)


@dataclass
class DiscoveryQueue:
    """Untrusted proposals stay outside RuleBook; no automatic promotion."""
    proposals: list[dict] = field(default_factory=list)

    def propose(self, statement: str, *, source_ids=(), falsification=""):
        if not statement.strip():
            raise ValueError("Empty proposal")
        self.proposals.append({"statement": statement, "source_ids": list(source_ids),
                               "falsification": falsification, "status": "unverified"})

    def ingest_concepts(self, tree):
        for c in tree.concepts:
            self.propose(c.formal or c.definition, source_ids=(c.id,),
                         falsification="Requires typed translation and rule review")


def load_reasoning_problem(data: dict):
    """JSON adapter; status must be assigned explicitly for every rule."""
    def atom(row):
        return Atom(row["predicate"], tuple(row.get("args", ())))
    rules = [Rule(r["id"], tuple(atom(p) for p in r["premises"]), atom(r["conclusion"]),
                  tuple(sorted(r.get("variables", {}).items())),
                  r.get("source", ""), r.get("status", "candidate"),
                  r.get("concept_id", ""), r.get("concept_sha256", ""),
                  r.get("mapping_review", ""))
             for r in data["rules"]]
    book = RuleBook(data["signatures"], data["objects"], rules)
    return book, frozenset(atom(a) for a in data["assumptions"]), atom(data["goal"])


def load_certificate(data: dict) -> Certificate:
    def atom(row):
        return Atom(row["predicate"], tuple(row.get("args", ())))
    steps = tuple(Hyperedge(e["rule_id"], tuple(tuple(v) for v in e["binding"]),
                           tuple(atom(p) for p in e["premises"]), atom(e["conclusion"]))
                  for e in data["steps"])
    return Certificate(atom(data["goal"]), frozenset(atom(a) for a in data["assumptions"]),
                       steps, data["rulebook_sha256"])
