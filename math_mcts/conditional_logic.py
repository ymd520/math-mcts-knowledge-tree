"""Nonrecursive conditional equational rewriting with checked guard proofs.

A conditional rule 'G1,...,Gk => L=R' applies only if EACH instantiated
ground guard Gi has a separately replayable equational proof from the
UNCHANGED unconditional EquationBook (and explicitly provided assumptions).
Conditional rules can never bootstrap their own guards. Both directions of
an established equality may be used; candidates are never executable.

This is a deliberately restricted, many-sorted first-order equality calculus,
not a general conditional-rewriting decision procedure.
"""
from __future__ import annotations
from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json

from .equational import (
    Equation, EquationBook, RewriteCertificate, RewriteRule, RewriteStep, Term,
    _available_rules, _instantiate, _match, _positions, _replace, _size,
    _subterm, _vars, prove_equation, verify_rewrite_certificate
)


@dataclass(frozen=True)
class ConditionalRule:
    id: str
    equation: Equation
    variables: tuple[tuple[str, str], ...]
    guards: tuple[Equation, ...]
    source: str
    status: str = "candidate"
    concept_id: str = ""
    concept_sha256: str = ""
    mapping_review: str = ""

    def __post_init__(self):
        object.__setattr__(self, "variables", tuple(tuple(x) for x in self.variables))
        object.__setattr__(self, "guards", tuple(self.guards))


@dataclass(frozen=True)
class GuardedStep:
    rewrite: RewriteStep
    guards: tuple[RewriteCertificate, ...] = ()


@dataclass(frozen=True)
class GuardedCertificate:
    goal: Equation
    assumptions: tuple[Equation, ...]
    steps: tuple[GuardedStep, ...]
    rulebook_sha256: str


@dataclass(frozen=True)
class GuardedResult:
    status: str
    certificate: GuardedCertificate | None
    expanded_states: int
    generated_states: int
    attempted_guards: int
    depth: int


class ConditionalBook:
    def __init__(self, base: EquationBook, rules: list[ConditionalRule]):
        self.base = base
        self.rules = {}
        self.candidates = {}
        for rule in rules:
            if (not rule.id or rule.id.startswith("@assumption:")
                or rule.id in base.rules or rule.id in base.candidates
                or rule.id in self.rules or rule.id in self.candidates):
                raise ValueError("invalid, reserved or duplicate conditional rule id")
            if not rule.guards or not rule.source.strip():
                raise ValueError("conditional rule needs guards and provenance")
            vars_ = dict(rule.variables)
            if (len(vars_) != len(rule.variables) or
                any(not name.startswith("?") or sort not in base.sorts
                    for name, sort in vars_.items())):
                raise ValueError("invalid conditional variable declarations")
            base.validate_equation(rule.equation, vars_)
            for guard in rule.guards:
                base.validate_equation(guard, vars_)
            lhs_vars = _vars(rule.equation.left)
            rhs_vars = _vars(rule.equation.right)
            guarded_vars = set().union(
                *(_vars(g.left) | _vars(g.right) for g in rule.guards))
            if lhs_vars != rhs_vars or lhs_vars != set(vars_) or not guarded_vars <= lhs_vars:
                raise ValueError("condition cannot invent witnesses; both sides must bind every variable")
            if rule.status == "reviewed":
                if rule.concept_id and not (rule.concept_sha256 and rule.mapping_review):
                    raise ValueError("mapped reviewed condition requires source snapshot and mapping review")
                self.rules[rule.id] = rule
            elif rule.status in {"candidate", "refuted"}:
                self.candidates[rule.id] = rule
            else:
                raise ValueError("invalid conditional rule status")

    def fingerprint(self):
        payload = {"base": self.base.fingerprint(),
                   "rules": [asdict(self.rules[k]) for k in sorted(self.rules)]}
        return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                         ensure_ascii=False).encode()).hexdigest()


def _ground(eq: Equation, binding: dict[str, Term]) -> Equation:
    return Equation(_instantiate(eq.left, binding), _instantiate(eq.right, binding))


def verify_guarded_certificate(book: ConditionalBook, cert: GuardedCertificate,
                               goal: Equation, *,
                               assumptions: tuple[Equation, ...] = ()) -> bool:
    """Independent proof replay: neither BFS caches nor search flags trusted."""
    try:
        if (not isinstance(cert, GuardedCertificate) or cert.goal != goal
            or cert.assumptions != tuple(assumptions)
            or cert.rulebook_sha256 != book.fingerprint()):
            return False
        base = book.base
        base.validate_equation(goal)
        assumptions = tuple(assumptions)
        for a in assumptions:
            base.validate_equation(a)
        ordinary = _available_rules(base, assumptions)
        current = goal.left
        for evidence in cert.steps:
            if not isinstance(evidence, GuardedStep):
                return False
            step = evidence.rewrite
            if step.before != current or type(step.reverse) is not bool:
                return False
            rule = book.rules.get(step.rule_id)
            if rule is not None:
                eq, variables, guards = rule.equation, rule.variables, rule.guards
            elif step.rule_id in ordinary:
                item = ordinary[step.rule_id]
                eq, variables, guards = item.equation, item.variables, ()
            else:
                return False
            source = eq.right if step.reverse else eq.left
            target = eq.left if step.reverse else eq.right
            binding = {}
            subterm = _subterm(current, step.position)
            if not _match(source, subterm, binding):
                return False
            if step.binding != tuple(sorted(binding.items())):
                return False
            if any(base.sort_of(binding[name]) != sort for name, sort in variables):
                return False
            if len(evidence.guards) != len(guards):
                return False
            for condition, witness in zip(guards, evidence.guards):
                required = _ground(condition, binding)
                if not verify_rewrite_certificate(base, witness, required, assumptions):
                    return False
            after = _replace(current, step.position, _instantiate(target, binding))
            if after == current or step.after != after:
                return False
            if base.sort_of(after) != base.sort_of(current):
                return False
            current = after
        return current == goal.right
    except (TypeError, KeyError, ValueError, AttributeError, RecursionError):
        return False


def prove_guarded(book: ConditionalBook, goal: Equation, *,
                  assumptions: tuple[Equation, ...] = (),
                  max_steps: int = 6, max_states: int = 1000,
                  max_term_nodes: int = 100, max_guard_steps: int = 4,
                  max_guard_states: int = 200, max_guard_attempts: int = 300) -> GuardedResult:
    budgets = ((max_steps, 0), (max_states, 1), (max_term_nodes, 1),
               (max_guard_steps, 0), (max_guard_states, 1),
               (max_guard_attempts, 1))
    if any(type(n) is not int or n < lower for n, lower in budgets):
        raise ValueError("invalid guarded rewrite search budgets")
    base = book.base
    base.validate_equation(goal)
    assumptions = tuple(assumptions)
    for a in assumptions:
        base.validate_equation(a)
    if _size(goal.left) > max_term_nodes or _size(goal.right) > max_term_nodes:
        return GuardedResult("term_size_budget", None, 0, 0, 0, 0)

    def certified(path, count, attempts):
        certificate = GuardedCertificate(goal, assumptions, tuple(path), book.fingerprint())
        if not verify_guarded_certificate(book, certificate, goal, assumptions=assumptions):
            raise RuntimeError("conditional proof failed independent replay")
        return GuardedResult("proved_relative_to_conditional_equalities",
                             certificate, count, len(seen), attempts,
                             len(certificate.steps))

    seen = {goal.left: None}
    if goal.left == goal.right:
        return certified((), 0, 0)
    rule_items = list(_available_rules(base, assumptions).items()) + list(book.rules.items())
    frontier = deque([(goal.left, 0)])
    parent = {}
    guard_cache = {}
    expanded = 0
    attempts = 0
    truncated = False

    while frontier and expanded < max_states:
        current, depth = frontier.popleft()
        expanded += 1
        if depth >= max_steps:
            continue
        for position, subterm in _positions(current):
            for rule_id, rule in rule_items:
                guards = rule.guards if isinstance(rule, ConditionalRule) else ()
                for reverse in (False, True):
                    pattern = rule.equation.right if reverse else rule.equation.left
                    replacement = rule.equation.left if reverse else rule.equation.right
                    bindings = {}
                    if not _match(pattern, subterm, bindings):
                        continue
                    if any(base.sort_of(bindings[name]) != sort
                           for name, sort in rule.variables):
                        continue
                    try:
                        after = _replace(current, position, _instantiate(replacement, bindings))
                        if base.sort_of(after) != base.sort_of(current):
                            continue
                    except (ValueError, KeyError):
                        continue
                    if after == current or after in seen or _size(after) > max_term_nodes:
                        continue
                    if len(seen) >= max_states:
                        truncated = True
                        continue
                    guard_proofs = []
                    valid = True
                    for condition in guards:
                        concrete = _ground(condition, bindings)
                        if concrete not in guard_cache:
                            if attempts >= max_guard_attempts:
                                truncated = True
                                valid = False
                                break
                            attempts += 1
                            result = prove_equation(base, concrete, assumptions=assumptions,
                                                     max_steps=max_guard_steps,
                                                     max_states=max_guard_states,
                                                     max_term_nodes=max_term_nodes)
                            guard_cache[concrete] = result.certificate
                        proof = guard_cache[concrete]
                        if proof is None:
                            valid = False
                            break
                        guard_proofs.append(proof)
                    if not valid:
                        continue
                    step = GuardedStep(
                        RewriteStep(rule_id, reverse, position,
                                    tuple(sorted(bindings.items())), current, after),
                        tuple(guard_proofs))
                    seen[after] = None
                    parent[after] = (current, step)
                    if after == goal.right:
                        steps = []
                        cur = after
                        while cur != goal.left:
                            previous, evidence = parent[cur]
                            steps.append(evidence)
                            cur = previous
                        return certified(reversed(steps), expanded, attempts)
                    frontier.append((after, depth + 1))
    return GuardedResult("not_found_within_budget", None, expanded,
                         len(seen), attempts, 0)
