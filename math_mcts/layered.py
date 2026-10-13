"""Synchronous multi-premise collision layers with explicit breadth/depth checks.

Each layer consumes >= min_knowledge distinct premise atoms. At least one
premise of every edge comes from the preceding frontier; same-layer outputs
cannot be used until the next layer. MCTS selects bounded batches, not all
subsets of the knowledge corpus. Validity is relative to reviewed Horn rules.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from .mcts import Problem, mcts
from .reasoning import Atom, Hyperedge, RuleBook, load_reasoning_problem


@dataclass(frozen=True)
class LayerConfig:
    min_knowledge: int = 20
    min_layers: int = 20
    max_layers: int = 20
    batch_width: int = 20
    max_candidates: int = 2000
    batch_choices: int = 8

    def __post_init__(self):
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 1
               for v in asdict(self).values()):
            raise ValueError("Positive integer layer budgets required")
        if self.min_knowledge < 20 or self.min_layers < 20:
            raise ValueError("Layered mode requires >=20 knowledge points and >=20 layers")
        if self.max_layers < self.min_layers or self.max_candidates < self.batch_width:
            raise ValueError("Inconsistent layer budgets")


@dataclass(frozen=True)
class CollisionLayer:
    edges: tuple[Hyperedge, ...]

    @property
    def inputs(self):
        return frozenset(p for e in self.edges for p in e.premises)


@dataclass(frozen=True)
class LayerState:
    facts: frozenset[Atom]
    frontier: frozenset[Atom]
    layers: tuple[CollisionLayer, ...] = ()


@dataclass(frozen=True)
class LayerCertificate:
    assumptions: frozenset[Atom]
    goals: tuple[Atom, ...]
    config: LayerConfig
    layers: tuple[CollisionLayer, ...]
    rulebook_sha256: str


def replay_layers(book, certificate, expected_assumptions, expected_goals,
                  expected_config):
    """Return replay metrics, or None for any invalid/counterfeit certificate."""
    if (certificate.assumptions != frozenset(expected_assumptions)
            or certificate.goals != tuple(expected_goals)
            or certificate.config != expected_config
            or certificate.rulebook_sha256 != book.fingerprint()):
        return None
    cfg = certificate.config
    if not cfg.min_layers <= len(certificate.layers) <= cfg.max_layers:
        return None
    try:
        facts = set(certificate.assumptions)
        for atom in (*facts, *certificate.goals):
            book.validate_atom(atom)
        frontier = set(facts)
        depths = {a: 0 for a in facts}
        rows = []
        for number, layer in enumerate(certificate.layers, 1):
            if not 1 <= len(layer.edges) <= cfg.batch_width:
                return None
            outputs = {e.conclusion for e in layer.edges}
            if len(outputs) != len(layer.edges) or outputs & facts:
                return None
            if len(layer.inputs) < cfg.min_knowledge:
                return None
            next_depths = {}
            for edge in layer.edges:
                if book.instantiate(edge.rule_id, dict(edge.binding)) != edge:
                    return None
                if not set(edge.premises) <= facts or not set(edge.premises) & frontier:
                    return None
                next_depths[edge.conclusion] = 1 + max(depths[p] for p in edge.premises)
            rows.append({"layer": number, "participating_knowledge": len(layer.inputs),
                         "previous_frontier_inputs": len(layer.inputs & frontier),
                         "rule_applications": len(layer.edges),
                         "new_conclusions": len(outputs),
                         "max_dependency_depth": max(next_depths.values())})
            depths.update(next_depths)
            facts.update(outputs)
            frontier = outputs
        if not certificate.goals or not set(certificate.goals) <= facts:
            return None
        goal_depth = max(depths[g] for g in certificate.goals)
        if goal_depth < cfg.min_layers:
            return None
        # Distinguish all explored conclusions from the goal proof dependency cone.
        producers = {e.conclusion: (i, e) for i, l in enumerate(certificate.layers)
                     for e in l.edges}
        relevant = set()
        pending = list(certificate.goals)
        while pending:
            atom = pending.pop()
            if atom in relevant or atom in certificate.assumptions:
                continue
            relevant.add(atom)
            pending.extend(producers[atom][1].premises)
        for i, row in enumerate(rows):
            edges = [e for e in certificate.layers[i].edges if e.conclusion in relevant]
            row["goal_relevant_rules"] = len(edges)
            row["goal_relevant_knowledge"] = len({p for e in edges for p in e.premises})
            if row["goal_relevant_knowledge"] < cfg.min_knowledge:
                return None
        return {"effective_goal_depth": goal_depth, "layers": rows,
                "applied_rules": sum(len(l.edges) for l in certificate.layers),
                "goal_relevant_rules": len(relevant)}
    except (KeyError, ValueError, TypeError):
        return None


class LayeredProblem(Problem):
    def __init__(self, book, assumptions, goals, config):
        self.book, self.assumptions, self.goals, self.config = book, assumptions, goals, config
        selected = {r.id: r for g in goals for r in book.backward_rules(g)}
        self.rules = tuple(selected[k] for k in sorted(selected))
        self.best = None
        self.cache = {}
        self.shortages = set()
        self.candidate_truncated = False
        self.max_reached = 0

    def initial_state(self):
        return LayerState(self.assumptions, self.assumptions)

    def actions(self, state):
        if len(state.layers) >= self.config.max_layers or set(self.goals) <= state.facts:
            return []
        key = (state.facts, state.frontier)
        if key in self.cache:
            return list(self.cache[key])
        candidates = []
        seen = set()
        stop = False
        index = {}
        for atom in sorted(state.facts):
            index.setdefault(atom.predicate, []).append(atom)
        for rule in self.rules:
            for edge in self.book.matches(rule, state.facts, fact_index=index):
                if edge.conclusion in state.facts or not set(edge.premises) & state.frontier:
                    continue
                if edge in seen:
                    continue
                if len(candidates) >= self.config.max_candidates:
                    self.candidate_truncated = True
                    stop = True
                    break
                seen.add(edge)
                candidates.append(edge)
            if stop:
                break
        batches = []
        # Bounded alternative rotations; never enumerate 2^N subsets.
        for offset in range(min(self.config.batch_choices, len(candidates))):
            chosen, outputs = [], set()
            for edge in candidates[offset:] + candidates[:offset]:
                if edge.conclusion in outputs:
                    continue
                chosen.append(edge)
                outputs.add(edge.conclusion)
                if len(chosen) == self.config.batch_width:
                    break
            batch = CollisionLayer(tuple(sorted(chosen, key=lambda e: (e.rule_id, e.binding, e.conclusion))))
            if len(batch.inputs) >= self.config.min_knowledge and batch not in batches:
                batches.append(batch)
        if not batches:
            self.shortages.add((len(state.layers) + 1, len(candidates),
                                len({p for e in candidates for p in e.premises})))
        self.cache[key] = tuple(batches)
        return batches

    def step(self, state, action):
        if action not in self.actions(state):
            raise ValueError("Invalid collision batch")
        outputs = frozenset(e.conclusion for e in action.edges)
        next_state = LayerState(state.facts | outputs, outputs, state.layers + (action,))
        self.max_reached = max(self.max_reached, len(next_state.layers))
        return next_state

    def terminal(self, state):
        return not self.actions(state)

    def reward(self, state):
        if len(state.layers) < self.config.min_layers or not set(self.goals) <= state.facts:
            return 0.0
        cert = LayerCertificate(self.assumptions, self.goals, self.config, state.layers,
                                self.book.fingerprint())
        metrics = replay_layers(self.book, cert, self.assumptions, self.goals, self.config)
        if metrics is None:
            return 0.0
        self.best = cert
        return 1.0


def derive_layers(book: RuleBook, assumptions, goals, *, config=None,
                  iterations=50, seed=7):
    cfg = config or LayerConfig()
    if not isinstance(iterations, int) or iterations < 1:
        raise ValueError("Positive iterations required")
    assumptions, goals = frozenset(assumptions), tuple(goals)
    if not goals or len(set(goals)) != len(goals):
        raise ValueError("Nonempty distinct goals required")
    for atom in (*assumptions, *goals):
        book.validate_atom(atom)
    problem = LayeredProblem(book, assumptions, goals, cfg)
    mcts(problem, iterations=iterations, max_depth=cfg.max_layers, seed=seed)
    metrics = (replay_layers(book, problem.best, assumptions, goals, cfg)
               if problem.best else None)
    return {"status": "derived_relative_to_rules" if metrics else "not_found_within_budget",
            "certificate": problem.best, "metrics": metrics,
            "iterations": iterations, "seed": seed, "max_layers_reached": problem.max_reached,
            "candidate_truncated": problem.candidate_truncated,
            "shortages": [{"layer": l, "enabled_edges": e, "available_knowledge": k}
                          for l, e, k in sorted(problem.shortages)],
            "search_complete": False,
            "scope": "bounded batches over reviewed function-free Horn rules"}


def load_layered_problem(data):
    # Reuse the existing typed JSON adapter; multiple goals are explicit.
    rows = data.get("goals") or [data["goal"]]
    book, assumptions, _ = load_reasoning_problem({**data, "goal": rows[0]})
    goals = tuple(Atom(g["predicate"], tuple(g.get("args", ()))) for g in rows)
    return book, assumptions, goals, LayerConfig(**data.get("layer_config", {}))


def load_layer_certificate(data):
    from .reasoning import load_certificate
    dummy = load_certificate({"goal": data["goals"][0], "assumptions": data["assumptions"],
                              "steps": [], "rulebook_sha256": data["rulebook_sha256"]})
    layers = []
    for layer in data["layers"]:
        flat = load_certificate({"goal": data["goals"][0], "assumptions": data["assumptions"],
                                 "steps": layer["edges"], "rulebook_sha256": data["rulebook_sha256"]})
        layers.append(CollisionLayer(flat.steps))
    return LayerCertificate(dummy.assumptions,
                            tuple(Atom(g["predicate"], tuple(g.get("args", ()))) for g in data["goals"]),
                            LayerConfig(**data["config"]), tuple(layers), data["rulebook_sha256"])


def report_json(result):
    import json
    def default(value):
        if isinstance(value, frozenset):
            return [asdict(a) for a in sorted(value)]
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        raise TypeError(type(value).__name__)
    return json.dumps(result, default=default, ensure_ascii=False, indent=2)
