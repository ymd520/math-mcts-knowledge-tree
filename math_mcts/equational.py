"""A small, typed, proof-producing *equational* logic kernel.

Architecture boundary: equational reasoning is independent of the legacy
function-free Horn engine. Reviewed identities are assumptions supplied by
the caller, NOT verified mathematical truths or Lean kernel certificates.

Terms are first-order and fully typed. Rewriting is permitted inside any
function application (congruence); equation direction is symmetric.
Unreviewed candidates are never executable. No quantifiers, conditions,
partial functions, binding operators, or automatic source translation.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True, order=True)
class Term:
    kind: str
    symbol: str
    args: tuple["Term", ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "args", tuple(self.args))
        if self.kind not in {"var", "const", "app"}:
            raise ValueError("term kind must be var, const or app")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("nonempty term symbol required")
        if self.kind == "var" and not self.symbol.startswith("?"):
            raise ValueError("variable names must begin with ?")
        if self.kind != "var" and self.symbol.startswith("?"):
            raise ValueError("functions and constants cannot look like variables")
        if self.kind != "app" and self.args:
            raise ValueError("only applications may carry arguments")
        if any(not isinstance(item, Term) for item in self.args):
            raise ValueError("nested terms must be Term instances")

    @classmethod
    def var(cls, symbol: str) -> "Term":
        return cls("var", symbol)

    @classmethod
    def const(cls, symbol: str) -> "Term":
        return cls("const", symbol)

    @classmethod
    def app(cls, symbol: str, *args: "Term") -> "Term":
        return cls("app", symbol, args)


@dataclass(frozen=True)
class Equation:
    left: Term
    right: Term


@dataclass(frozen=True)
class RewriteRule:
    id: str
    equation: Equation
    variables: tuple[tuple[str, str], ...] = ()
    source: str = ""
    status: str = "candidate"
    concept_id: str = ""
    concept_sha256: str = ""
    mapping_review: str = ""

    def __post_init__(self):
        object.__setattr__(self, "variables", tuple(tuple(x) for x in self.variables))


@dataclass(frozen=True)
class RewriteStep:
    rule_id: str
    reverse: bool
    position: tuple[int, ...]
    binding: tuple[tuple[str, Term], ...]
    before: Term
    after: Term


@dataclass(frozen=True)
class RewriteCertificate:
    goal: Equation
    assumptions: tuple[Equation, ...]
    steps: tuple[RewriteStep, ...]
    rulebook_sha256: str


@dataclass(frozen=True)
class RewriteResult:
    status: str
    certificate: RewriteCertificate | None
    expanded_states: int
    generated_states: int
    depth: int
    scope_exhausted: bool


def _vars(term: Term) -> set[str]:
    found = set()
    pending = [term]
    while pending:
        current = pending.pop()
        if current.kind == "var":
            found.add(current.symbol)
        else:
            pending.extend(current.args)
    return found


def _size(term: Term) -> int:
    count = 0
    pending = [term]
    while pending:
        current = pending.pop()
        count += 1
        pending.extend(current.args)
    return count


class EquationBook:
    """Explicit sorts, function signatures and reviewed equality identities."""

    def __init__(self, sorts, constants: Mapping[str, str],
                 functions: Mapping[str, tuple[tuple[str, ...], str]],
                 rules: list[RewriteRule]):
        self.sorts = frozenset(sorts)
        if not self.sorts or any(not isinstance(s, str) or not s for s in self.sorts):
            raise ValueError("sorts must be nonempty names")
        self.constants = dict(constants)
        self.functions = {k: (tuple(argtypes), result)
                          for k, (argtypes, result) in functions.items()}
        if set(self.constants) & set(self.functions):
            raise ValueError("symbol cannot be both function and constant")
        for symbol, sort in self.constants.items():
            if not symbol or symbol.startswith("?") or sort not in self.sorts:
                raise ValueError("invalid typed constant")
        for symbol, (args, result) in self.functions.items():
            if (not symbol or symbol.startswith("?") or
                result not in self.sorts or any(s not in self.sorts for s in args)):
                raise ValueError("invalid function signature")
        self.rules: dict[str, RewriteRule] = {}
        self.candidates: dict[str, RewriteRule] = {}
        for rule in rules:
            if not rule.id or rule.id.startswith("@assumption:"):
                raise ValueError("invalid or reserved rewrite rule id")
            if rule.id in self.rules or rule.id in self.candidates:
                raise ValueError("duplicate rewrite rule id")
            vars_ = dict(rule.variables)
            if (len(vars_) != len(rule.variables) or
                any(not k.startswith("?") or v not in self.sorts
                    for k, v in vars_.items())):
                raise ValueError("invalid typed variables")
            self.validate_equation(rule.equation, vars_)
            # Symmetric rewrites cannot freely create witnesses. Every
            # schematic variable must occur on BOTH sides of the identity.
            left_vars = _vars(rule.equation.left)
            right_vars = _vars(rule.equation.right)
            if left_vars != right_vars or left_vars != set(vars_):
                raise ValueError("both sides must bind exactly the same variables")
            if rule.status == "reviewed":
                if not rule.source.strip():
                    raise ValueError("reviewed identity requires provenance")
                if rule.concept_id and not (rule.concept_sha256 and rule.mapping_review):
                    raise ValueError("mapped reviewed identity needs statement hash and review")
                self.rules[rule.id] = rule
            elif rule.status in {"candidate", "refuted"}:
                self.candidates[rule.id] = rule
            else:
                raise ValueError("unknown rewrite rule status")

    def sort_of(self, term: Term, variables: Mapping[str, str] | None = None) -> str:
        variables = {} if variables is None else variables
        if not isinstance(term, Term):
            raise ValueError("expected a Term instance")
        if term.kind == "var":
            sort = variables.get(term.symbol)
            if sort not in self.sorts:
                raise ValueError("undeclared variable or invalid variable sort")
            return sort
        if term.kind == "const":
            if term.symbol not in self.constants:
                raise ValueError("undeclared constant")
            return self.constants[term.symbol]
        signature = self.functions.get(term.symbol)
        if signature is None:
            raise ValueError("undeclared function")
        required, result = signature
        if len(required) != len(term.args):
            raise ValueError("wrong function arity")
        if any(self.sort_of(arg, variables) != expected
               for arg, expected in zip(term.args, required)):
            raise ValueError("function argument sort mismatch")
        return result

    def validate_equation(self, eq: Equation, variables=None) -> None:
        if not isinstance(eq, Equation) or self.sort_of(eq.left, variables) != self.sort_of(eq.right, variables):
            raise ValueError("equation terms must have the same declared sort")

    def fingerprint(self) -> str:
        payload = {
            "sorts": sorted(self.sorts), "constants": self.constants,
            "functions": self.functions,
            "rules": [asdict(self.rules[k]) for k in sorted(self.rules)],
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                         sort_keys=True).encode("utf-8")).hexdigest()


def _subterm(term: Term, position: tuple[int, ...]) -> Term:
    part = term
    for index in position:
        if type(index) is not int or index < 0 or part.kind != "app" or index >= len(part.args):
            raise ValueError("invalid rewrite position")
        part = part.args[index]
    return part


def _replace(term: Term, position: tuple[int, ...], replacement: Term) -> Term:
    if not position:
        return replacement
    index = position[0]
    if type(index) is not int or index < 0 or term.kind != "app" or index >= len(term.args):
        raise ValueError("invalid rewrite position")
    args = list(term.args)
    args[index] = _replace(args[index], position[1:], replacement)
    return Term.app(term.symbol, *args)


def _positions(term: Term):
    pending = [((), term)]
    while pending:
        pos, item = pending.pop()
        yield pos, item
        for i in reversed(range(len(item.args))):
            pending.append((pos + (i,), item.args[i]))


def _match(pattern: Term, ground: Term, binding: dict[str, Term]) -> bool:
    if pattern.kind == "var":
        existing = binding.get(pattern.symbol)
        if existing is not None:
            return existing == ground
        binding[pattern.symbol] = ground
        return True
    if pattern.kind != ground.kind or pattern.symbol != ground.symbol or len(pattern.args) != len(ground.args):
        return False
    return all(_match(p, g, binding) for p, g in zip(pattern.args, ground.args))


def _instantiate(term: Term, binding: Mapping[str, Term]) -> Term:
    if term.kind == "var":
        return binding[term.symbol]
    if term.kind == "const":
        return term
    return Term.app(term.symbol, *(_instantiate(a, binding) for a in term.args))


def _available_rules(book: EquationBook, assumptions: tuple[Equation, ...]):
    result = dict(book.rules)
    for i, eq in enumerate(assumptions):
        result[f"@assumption:{i}"] = RewriteRule(
            f"@assumption:{i}", eq, (), "explicit local equality assumption", "reviewed")
    return result


def verify_rewrite_certificate(book: EquationBook, certificate: RewriteCertificate,
                               goal: Equation,
                               assumptions: tuple[Equation, ...] = ()) -> bool:
    """Replay every typed and source-locked contextual equality transformation.

    Verification does not consult BFS's visited states, heuristics or parents.
    This is a checked derivation *relative to* the given source identities.
    """
    assumptions = tuple(assumptions)
    if (certificate.goal != goal or certificate.assumptions != assumptions
            or certificate.rulebook_sha256 != book.fingerprint()):
        return False
    try:
        book.validate_equation(goal)
        for eq in assumptions:
            book.validate_equation(eq)
        rules = _available_rules(book, assumptions)
        current = goal.left
        for step in certificate.steps:
            if not isinstance(step, RewriteStep) or step.before != current:
                return False
            rule = rules.get(step.rule_id)
            if rule is None:
                return False
            binding = {}
            original = rule.equation.right if step.reverse else rule.equation.left
            replacement = rule.equation.left if step.reverse else rule.equation.right
            if not _match(original, _subterm(current, step.position), binding):
                return False
            if step.binding != tuple(sorted(binding.items())):
                return False
            before_sort = book.sort_of(_subterm(current, step.position))
            if before_sort != book.sort_of(_instantiate(replacement, binding)):
                return False
            updated = _replace(current, step.position, _instantiate(replacement, binding))
            if updated == current or updated != step.after:
                return False
            book.sort_of(updated)
            current = updated
        return current == goal.right
    except (TypeError, ValueError, KeyError, RecursionError):
        return False


def prove_equation(book: EquationBook, goal: Equation, *,
                   assumptions: tuple[Equation, ...] = (),
                   max_steps: int = 6, max_states: int = 4000,
                   max_term_nodes: int = 100) -> RewriteResult:
    """Bounded BFS in a typed equational rewrite space.

    A budget miss NEVER refutes the equation. This is not a complete solver
    of equational theories and is not a proof of rule provenance.
    """
    if (type(max_steps) is not int or max_steps < 0
            or type(max_states) is not int or max_states < 1
            or type(max_term_nodes) is not int or max_term_nodes < 1):
        raise ValueError("invalid equational search budget")
    assumptions = tuple(assumptions)
    book.validate_equation(goal)      # no free query variables
    for eq in assumptions:
        book.validate_equation(eq)    # local assumptions MUST be ground
    if _size(goal.left) > max_term_nodes or _size(goal.right) > max_term_nodes:
        return RewriteResult("term_size_budget", None, 0, 0, 0, True)
    fp = book.fingerprint()
    if goal.left == goal.right:
        cert = RewriteCertificate(goal, assumptions, (), fp)
        assert verify_rewrite_certificate(book, cert, goal, assumptions)
        return RewriteResult("proved_relative_to_equalities", cert, 0, 1, 0, False)
    rules = _available_rules(book, assumptions)
    frontier = deque([goal.left])
    parent: dict[Term, tuple[Term, RewriteStep] | None] = {goal.left: None}
    distances = {goal.left: 0}
    expanded = 0
    truncated = False
    while frontier:
        if expanded >= max_states:
            truncated = True
            break
        current = frontier.popleft()
        distance = distances[current]
        expanded += 1
        if distance >= max_steps:
            if any(True for _ in rules):
                truncated = True
            continue
        for position, subterm in _positions(current):
            for rule in rules.values():
                for reverse in (False, True):
                    source = rule.equation.right if reverse else rule.equation.left
                    target = rule.equation.left if reverse else rule.equation.right
                    binding: dict[str, Term] = {}
                    if not _match(source, subterm, binding):
                        continue
                    updated = _replace(current, position, _instantiate(target, binding))
                    if updated == current or updated in parent:
                        continue
                    if _size(updated) > max_term_nodes:
                        truncated = True
                        continue
                    if len(parent) >= max_states:
                        truncated = True
                        continue
                    step = RewriteStep(rule.id, reverse, position,
                                       tuple(sorted(binding.items())), current, updated)
                    parent[updated] = (current, step)
                    distances[updated] = distance + 1
                    if updated == goal.right:
                        backwards = []
                        node = updated
                        while parent[node] is not None:
                            previous, edge = parent[node]
                            backwards.append(edge)
                            node = previous
                        cert = RewriteCertificate(goal, assumptions, tuple(reversed(backwards)), fp)
                        if not verify_rewrite_certificate(book, cert, goal, assumptions):
                            raise RuntimeError("independent rewrite replay failed")
                        return RewriteResult("proved_relative_to_equalities", cert,
                                             expanded, len(parent), len(cert.steps), False)
                    frontier.append(updated)
    return RewriteResult("not_found_within_budget", None, expanded,
                         len(parent), 0, truncated)
