"""Explicit JSON contract for finite quantified and conditional equational tasks.

Search and certificate serialization live here; independent checkers reside
in finite_logic.py / conditional_logic.py and do not trust search output.
"""
from __future__ import annotations

from .conditional_logic import (
    ConditionalBook, ConditionalRule, GuardedCertificate, GuardedStep,
    prove_guarded, verify_guarded_certificate
)
from .finite_logic import (
    Formula, FiniteCertificate, FiniteProof,
    prove_finite, verify_finite_certificate
)
from .logic_router import (
    parse_term, term_data, parse_equation, equation_data,
    load_equational_book, certificate_data, load_rewrite_certificate
)
from .equational import Equation, RewriteStep


def parse_formula(data):
    if not isinstance(data, dict) or len(data) != 1:
        raise ValueError("formula needs exactly one explicit connective")
    tag, payload = next(iter(data.items()))
    if tag == "eq":
        return Formula.eqn(parse_equation(payload))
    if tag in {"and", "or"}:
        if not isinstance(payload, list):
            raise ValueError("and/or requires a list")
        children = tuple(parse_formula(x) for x in payload)
        return Formula.conj(*children) if tag == "and" else Formula.disj(*children)
    if tag in {"forall", "exists"}:
        if not isinstance(payload, dict) or set(payload) != {"var", "sort", "body"}:
            raise ValueError("explicit binder var, sort and body required")
        if not isinstance(payload["var"], str) or not isinstance(payload["sort"], str):
            raise ValueError("binder and sort must be names")
        body = parse_formula(payload["body"])
        return (Formula.forall(payload["var"], payload["sort"], body)
                if tag == "forall" else Formula.exists(payload["var"], payload["sort"], body))
    if tag == "implies":
        if not isinstance(payload, dict) or set(payload) != {"premises", "body"}:
            raise ValueError("guarded implication needs premises and body")
        if not isinstance(payload["premises"], list):
            raise ValueError("implication premises must be a list")
        return Formula.implies(tuple(parse_equation(x) for x in payload["premises"]),
                               parse_formula(payload["body"]))
    raise ValueError("unknown finite formula connective")


def formula_data(formula: Formula):
    if formula.kind == "eq":
        return {"eq": equation_data(formula.equation)}
    if formula.kind in {"and", "or"}:
        return {formula.kind: [formula_data(x) for x in formula.children]}
    if formula.kind == "implies":
        return {"implies": {"premises": [equation_data(x) for x in formula.premises],
                            "body": formula_data(formula.children[0])}}
    return {formula.kind: {"var": formula.variable, "sort": formula.sort,
                           "body": formula_data(formula.children[0])}}


def finite_proof_data(proof: FiniteProof):
    return {"kind": proof.kind, "witness": proof.witness,
            "equality": certificate_data(proof.equality) if proof.equality else None,
            "leaves": [finite_proof_data(p) for p in proof.leaves]}


def finite_certificate_data(cert: FiniteCertificate):
    return {"goal": formula_data(cert.goal), "assumptions": [equation_data(x) for x in cert.assumptions],
            "proof": finite_proof_data(cert.proof), "rulebook_sha256": cert.rulebook_sha256}


def load_finite_certificate(data):
    def parse_proof(p):
        if not isinstance(p, dict) or set(p) != {"kind", "witness", "equality", "leaves"}:
            raise ValueError("invalid finite proof tree")
        if not isinstance(p["witness"], str) or not isinstance(p["leaves"], list):
            raise ValueError("invalid witness or proof children")
        return FiniteProof(p["kind"], tuple(parse_proof(x) for x in p["leaves"]),
                           p["witness"], load_rewrite_certificate(p["equality"])
                           if p["equality"] is not None else None)
    return FiniteCertificate(parse_formula(data["goal"]),
                             tuple(parse_equation(x) for x in data["assumptions"]),
                             parse_proof(data["proof"]), data["rulebook_sha256"])


def load_conditional_problem(data):
    if not isinstance(data, dict) or data.get("logic") != "conditional_equational":
        raise ValueError("explicit conditional_equational selector required")
    base, assumptions = load_equational_book(data)
    cond = []
    for row in data["conditional_rules"]:
        cond.append(ConditionalRule(
            row["id"], parse_equation({"left": row["left"], "right": row["right"]}),
            tuple(sorted(row.get("variables", {}).items())),
            tuple(parse_equation(x) for x in row["guards"]),
            row.get("source", ""), row.get("status", "candidate"),
            row.get("concept_id", ""), row.get("concept_sha256", ""),
            row.get("mapping_review", "")))
    book = ConditionalBook(base, cond)
    goal = parse_equation(data["goal"])
    base.validate_equation(goal)
    return book, assumptions, goal


def guarded_certificate_data(cert: GuardedCertificate):
    return {
        "goal": equation_data(cert.goal), "assumptions": [equation_data(x) for x in cert.assumptions],
        "rulebook_sha256": cert.rulebook_sha256,
        "steps": [{
            "rewrite": {"rule_id": s.rewrite.rule_id, "reverse": s.rewrite.reverse,
                        "position": list(s.rewrite.position),
                        "binding": [[var, term_data(term)] for var, term in s.rewrite.binding],
                        "before": term_data(s.rewrite.before), "after": term_data(s.rewrite.after)},
            "guards": [certificate_data(g) for g in s.guards],
        } for s in cert.steps],
    }


def load_guarded_certificate(data):
    steps = []
    for x in data["steps"]:
        row = x["rewrite"]
        if type(row["reverse"]) is not bool or any(type(p) is not int for p in row["position"]):
            raise ValueError("invalid conditional rewrite direction or position")
        step = RewriteStep(
            row["rule_id"], row["reverse"], tuple(row["position"]),
            tuple((var, parse_term(term)) for var, term in row["binding"]),
            parse_term(row["before"]), parse_term(row["after"]))
        steps.append(GuardedStep(step, tuple(load_rewrite_certificate(g) for g in x["guards"])))
    return GuardedCertificate(
        parse_equation(data["goal"]), tuple(parse_equation(x) for x in data["assumptions"]),
        tuple(steps), data["rulebook_sha256"])


def solve_extended(data, *, max_steps, max_states, max_term_nodes,
                   max_cases=2000, max_nodes=5000, max_guard_attempts=300):
    kind = data.get("logic")
    if kind == "finite_equational":
        book, assumptions = load_equational_book(data)
        goal = parse_formula(data["goal"])
        result = prove_finite(
            book, goal, assumptions=assumptions,
            max_steps=max_steps, max_states=max_states, max_term_nodes=max_term_nodes,
            max_cases=max_cases, max_nodes=max_nodes)
        cert = result.certificate
        return {
            "logic": kind, "status": result.status,
            "certificate": finite_certificate_data(cert) if cert else None,
            "certificate_replayed": bool(cert),
            "attempted_equality_leaves": result.attempted_equality_leaves,
            "instantiated_quantifier_cases": result.instantiated_quantifier_cases,
            "certificate_nodes": result.certificate_nodes,
            "scope": "only explicitly declared finite constants; no infinite universal claim",
            "reviewed_rules": len(book.rules), "unverified_candidates": len(book.candidates),
        }
    if kind == "conditional_equational":
        book, assumptions, goal = load_conditional_problem(data)
        result = prove_guarded(book, goal, assumptions=assumptions,
                               max_steps=max_steps, max_states=max_states,
                               max_term_nodes=max_term_nodes,
                               max_guard_attempts=max_guard_attempts)
        cert = result.certificate
        return {
            "logic": kind, "status": result.status,
            "certificate": guarded_certificate_data(cert) if cert else None,
            "certificate_replayed": bool(cert), "expanded_states": result.expanded_states,
            "attempted_guards": result.attempted_guards,
            "depth": result.depth,
            "scope": "guard proofs checked from unconditional identities and explicit local assumptions only",
            "reviewed_rules": len(book.base.rules) + len(book.rules),
            "unverified_candidates": len(book.base.candidates) + len(book.candidates),
        }
    raise ValueError("unrecognized extended logic")


def verify_extended(data, report) -> bool:
    try:
        if not isinstance(data, dict) or not isinstance(report, dict):
            return False
        kind = data.get("logic")
        if kind != report.get("logic") or not isinstance(report.get("certificate"), dict):
            return False
        if kind == "finite_equational":
            book, assumptions = load_equational_book(data)
            goal = parse_formula(data["goal"])
            cert = load_finite_certificate(report["certificate"])
            return verify_finite_certificate(book, cert, goal, assumptions=assumptions)
        if kind == "conditional_equational":
            book, assumptions, goal = load_conditional_problem(data)
            cert = load_guarded_certificate(report["certificate"])
            return verify_guarded_certificate(book, cert, goal, assumptions=assumptions)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return False
    return False
