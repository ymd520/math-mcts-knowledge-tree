"""Proof-producing finite-domain fragment: =, and, or, forall, exists, implies.

This is NOT first-order universal reasoning over arbitrary mathematical
structures. Quantifiers range over the explicitly declared, finite constants
of the chosen sort. Equality leaves are proved using reviewed EquationBook
identities and explicit local assumptions; neither failure nor exhaustion
certifies a formula false. Independent replay checks every witness/instance.
"""
from __future__ import annotations
from dataclasses import dataclass
from .equational import (Equation, EquationBook, RewriteCertificate, Term,
                         prove_equation, verify_rewrite_certificate)


@dataclass(frozen=True)
class Formula:
    kind: str
    equation: Equation | None = None
    children: tuple["Formula", ...] = ()
    variable: str = ""
    sort: str = ""
    premises: tuple[Equation, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "children", tuple(self.children))
        object.__setattr__(self, "premises", tuple(self.premises))
        if self.kind == "eq":
            valid = (isinstance(self.equation, Equation) and not self.children
                     and not self.variable and not self.sort and not self.premises)
        elif self.kind in {"and", "or"}:
            valid = (len(self.children) > 0 and not self.variable and not self.sort
                     and self.equation is None and not self.premises)
        elif self.kind in {"forall", "exists"}:
            valid = (len(self.children) == 1 and self.variable.startswith("?")
                     and bool(self.sort) and self.equation is None and not self.premises)
        elif self.kind == "implies":
            valid = (len(self.children) == 1 and len(self.premises) > 0
                     and self.equation is None and not self.variable and not self.sort)
        else:
            valid = False
        if not valid or any(not isinstance(x, Formula) for x in self.children):
            raise ValueError("malformed finite equational formula")

    @staticmethod
    def eqn(eq: Equation): return Formula("eq", equation=eq)
    @staticmethod
    def conj(*children: "Formula"): return Formula("and", children=children)
    @staticmethod
    def disj(*children: "Formula"): return Formula("or", children=children)
    @staticmethod
    def forall(name: str, sort: str, body: "Formula"):
        return Formula("forall", children=(body,), variable=name, sort=sort)
    @staticmethod
    def exists(name: str, sort: str, body: "Formula"):
        return Formula("exists", children=(body,), variable=name, sort=sort)
    @staticmethod
    def implies(premises: tuple[Equation, ...], body: "Formula"):
        return Formula("implies", children=(body,), premises=premises)


@dataclass(frozen=True)
class FiniteProof:
    kind: str
    leaves: tuple["FiniteProof", ...] = ()
    witness: str = ""                    # exists: constant, or: child index string
    equality: RewriteCertificate | None = None


@dataclass(frozen=True)
class FiniteCertificate:
    goal: Formula
    assumptions: tuple[Equation, ...]
    proof: FiniteProof
    rulebook_sha256: str


@dataclass(frozen=True)
class FiniteResult:
    status: str
    certificate: FiniteCertificate | None
    attempted_equality_leaves: int
    instantiated_quantifier_cases: int
    certificate_nodes: int


def _subterm(term: Term, variable: str, value: Term) -> Term:
    if term.kind == "var":
        return value if term.symbol == variable else term
    if term.kind == "app":
        return Term.app(term.symbol, *(_subterm(t, variable, value) for t in term.args))
    return term


def _subeq(eq: Equation, variable: str, value: Term) -> Equation:
    return Equation(_subterm(eq.left, variable, value),
                    _subterm(eq.right, variable, value))


def instantiate_formula(formula: Formula, variable: str, constant: str) -> Formula:
    """Capture-safe because same-name nested binders are rejected by validator."""
    value = Term.const(constant)
    if formula.kind in {"forall", "exists"} and formula.variable == variable:
        return formula
    if formula.kind == "eq":
        return Formula.eqn(_subeq(formula.equation, variable, value))
    if formula.kind == "implies":
        return Formula.implies(
            tuple(_subeq(p, variable, value) for p in formula.premises),
            instantiate_formula(formula.children[0], variable, constant))
    children = tuple(instantiate_formula(c, variable, constant) for c in formula.children)
    return Formula(formula.kind, children=children,
                   variable=formula.variable, sort=formula.sort)


def validate_formula(book: EquationBook, formula: Formula, *,
                     max_depth: int = 40) -> None:
    """Check all free/bound variables and many-sorted terms before searching."""
    if not isinstance(formula, Formula) or type(max_depth) is not int or max_depth < 1:
        raise ValueError("invalid formula or validation depth")
    def walk(f, env, depth):
        if depth > max_depth:
            raise ValueError("formula nesting depth exceeds limit")
        if f.kind == "eq":
            book.validate_equation(f.equation, env)
            return
        if f.kind in {"forall", "exists"}:
            if f.sort not in book.sorts or f.variable in env:
                raise ValueError("invalid binder sort or shadowed variable")
            walk(f.children[0], {**env, f.variable: f.sort}, depth + 1)
            return
        if f.kind == "implies":
            for premise in f.premises:
                book.validate_equation(premise, env)
        for child in f.children:
            walk(child, env, depth + 1)
    walk(formula, {}, 1)


def _domain(book: EquationBook, sort: str) -> tuple[str, ...]:
    return tuple(sorted(name for name, s in book.constants.items() if s == sort))


def verify_finite_certificate(book: EquationBook, cert: FiniteCertificate,
                              goal: Formula, *,
                              assumptions: tuple[Equation, ...] = (),
                              max_nodes: int = 50000) -> bool:
    """Independent structural checker; no search, fallback, or certificate trust."""
    try:
        if (not isinstance(cert, FiniteCertificate) or cert.goal != goal
            or cert.assumptions != tuple(assumptions)
            or cert.rulebook_sha256 != book.fingerprint()
            or type(max_nodes) is not int or max_nodes < 1):
            return False
        validate_formula(book, goal)
        assumptions = tuple(assumptions)
        for a in assumptions:
            book.validate_equation(a)
        visited = 0
        def check(f, evidence, local):
            nonlocal visited
            visited += 1
            if visited > max_nodes or not isinstance(evidence, FiniteProof) or evidence.kind != f.kind:
                return False
            if f.kind == "eq":
                return (evidence.equality is not None and not evidence.leaves
                        and not evidence.witness and
                        verify_rewrite_certificate(book, evidence.equality, f.equation, local))
            if evidence.equality is not None:
                return False
            if f.kind == "implies":
                return (len(evidence.leaves) == 1 and not evidence.witness and
                        check(f.children[0], evidence.leaves[0], local + f.premises))
            if f.kind == "and":
                return (len(evidence.leaves) == len(f.children) and not evidence.witness
                        and all(check(c, p, local) for c,p in zip(f.children, evidence.leaves)))
            if f.kind == "or":
                if len(evidence.leaves) != 1 or not evidence.witness.isdecimal():
                    return False
                idx = int(evidence.witness)
                return (str(idx) == evidence.witness and 0 <= idx < len(f.children)
                        and check(f.children[idx], evidence.leaves[0], local))
            domain = _domain(book, f.sort)
            if f.kind == "forall":
                return (not evidence.witness and len(evidence.leaves) == len(domain)
                        and all(check(instantiate_formula(f.children[0], f.variable, obj),
                                      part, local)
                                for obj, part in zip(domain, evidence.leaves)))
            return (len(evidence.leaves) == 1 and evidence.witness in domain and
                    check(instantiate_formula(f.children[0], f.variable, evidence.witness),
                          evidence.leaves[0], local))
        return check(goal, cert.proof, assumptions)
    except (KeyError, TypeError, ValueError, RecursionError, AttributeError):
        return False


def prove_finite(book: EquationBook, goal: Formula, *,
                 assumptions: tuple[Equation, ...] = (),
                 max_steps: int = 6, max_states: int = 250,
                 max_term_nodes: int = 100,
                 max_cases: int = 2000, max_nodes: int = 5000) -> FiniteResult:
    """Conservative bounded enumeration; never a refutation on a miss."""
    if any(type(n) is not int or n < lower for n, lower in
           ((max_steps,0), (max_states,1), (max_term_nodes,1),
            (max_cases,1), (max_nodes,1))):
        raise ValueError("invalid finite logic budgets")
    validate_formula(book, goal)
    assumptions = tuple(assumptions)
    for a in assumptions:
        book.validate_equation(a)
    cases = 0
    leaves = 0
    nodes = 0
    exhausted = False

    def search(f, local):
        nonlocal cases, leaves, nodes, exhausted
        nodes += 1
        if nodes > max_nodes:
            exhausted = True
            return None
        if f.kind == "eq":
            leaves += 1
            result = prove_equation(book, f.equation, assumptions=local,
                                    max_steps=max_steps, max_states=max_states,
                                    max_term_nodes=max_term_nodes)
            if result.certificate is not None:
                return FiniteProof("eq", equality=result.certificate)
            return None
        if f.kind == "implies":
            p = search(f.children[0], local + f.premises)
            return FiniteProof("implies", leaves=(p,)) if p is not None else None
        if f.kind == "and":
            children = []
            for child in f.children:
                part = search(child, local)
                if part is None:
                    return None
                children.append(part)
            return FiniteProof("and", leaves=tuple(children))
        if f.kind == "or":
            for i, child in enumerate(f.children):
                part = search(child, local)
                if part is not None:
                    return FiniteProof("or", leaves=(part,), witness=str(i))
            return None
        domain = _domain(book, f.sort)
        if f.kind == "forall":
            results = []
            for obj in domain:
                cases += 1
                if cases > max_cases:
                    exhausted = True
                    return None
                part = search(instantiate_formula(f.children[0], f.variable, obj), local)
                if part is None:
                    return None
                results.append(part)
            return FiniteProof("forall", leaves=tuple(results))
        for obj in domain:
            cases += 1
            if cases > max_cases:
                exhausted = True
                return None
            part = search(instantiate_formula(f.children[0], f.variable, obj), local)
            if part is not None:
                return FiniteProof("exists", leaves=(part,), witness=obj)
        return None

    evidence = search(goal, assumptions)
    if evidence is None:
        return FiniteResult("not_found_within_finite_budget", None, leaves, cases, nodes)
    cert = FiniteCertificate(goal, assumptions, evidence, book.fingerprint())
    if not verify_finite_certificate(book, cert, goal, assumptions=assumptions,
                                     max_nodes=max_nodes):
        raise RuntimeError("finite proof failed independent replay")
    return FiniteResult("proved_relative_to_reviewed_equalities_over_declared_finite_domain",
                        cert, leaves, cases, nodes)
