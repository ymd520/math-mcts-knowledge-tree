"""Strict, explicit dispatch between distinct mathematical proof languages.

This is *not* an automatic translator or a source verifier. The problem
chooses its logic upfront: reviewed ground Horn rules or reviewed typed
equational identities. Candidates and refuted rules cannot be executed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import json

from .equational import (Equation, EquationBook, RewriteCertificate, RewriteRule,
                         RewriteStep, Term, prove_equation, verify_rewrite_certificate)
from .reasoning import derive, load_reasoning_problem, verify_certificate, load_certificate


def parse_term(data: Any) -> Term:
    if not isinstance(data, dict):
        raise ValueError("term must be an object")
    if set(data) == {"var"} and isinstance(data["var"], str):
        return Term.var(data["var"])
    if set(data) == {"const"} and isinstance(data["const"], str):
        return Term.const(data["const"])
    if set(data) == {"app", "args"} and isinstance(data["app"], str) and isinstance(data["args"], list):
        return Term.app(data["app"], *(parse_term(a) for a in data["args"]))
    raise ValueError("invalid explicit term syntax")


def term_data(term: Term) -> dict:
    if term.kind == "var":
        return {"var": term.symbol}
    if term.kind == "const":
        return {"const": term.symbol}
    return {"app": term.symbol, "args": [term_data(a) for a in term.args]}


def parse_equation(row: Any) -> Equation:
    if not isinstance(row, dict) or set(row) != {"left", "right"}:
        raise ValueError("equation must have exactly left and right")
    return Equation(parse_term(row["left"]), parse_term(row["right"]))


def equation_data(eq: Equation) -> dict:
    return {"left": term_data(eq.left), "right": term_data(eq.right)}


def load_equational_problem(data: dict):
    if not isinstance(data, dict) or data.get("logic") != "equational":
        raise ValueError("explicit equational logic selector required")
    signature = data["signature"]
    funcs = {
        name: (tuple(value["args"]), value["returns"])
        for name, value in signature["functions"].items()
    }
    rules = []
    for row in data["rules"]:
        rules.append(RewriteRule(
            row["id"], parse_equation({"left": row["left"], "right": row["right"]}),
            tuple(sorted(row.get("variables", {}).items())),
            row.get("source", ""), row.get("status", "candidate"),
            row.get("concept_id", ""), row.get("concept_sha256", ""),
            row.get("mapping_review", "")))
    book = EquationBook(signature["sorts"], signature["constants"], funcs, rules)
    assumptions = tuple(parse_equation(eq) for eq in data.get("assumptions", []))
    goal = parse_equation(data["goal"])
    book.validate_equation(goal)
    for eq in assumptions:
        book.validate_equation(eq)
    return book, assumptions, goal


def certificate_data(certificate: RewriteCertificate) -> dict:
    return {
        "goal": equation_data(certificate.goal),
        "assumptions": [equation_data(eq) for eq in certificate.assumptions],
        "rulebook_sha256": certificate.rulebook_sha256,
        "steps": [
            {
                "rule_id": step.rule_id,
                "reverse": step.reverse,
                "position": list(step.position),
                "binding": [[name, term_data(term)] for name, term in step.binding],
                "before": term_data(step.before), "after": term_data(step.after),
            }
            for step in certificate.steps
        ],
    }


def load_rewrite_certificate(data: dict) -> RewriteCertificate:
    if not isinstance(data, dict):
        raise ValueError("expected certificate object")
    steps = []
    for row in data["steps"]:
        if type(row["reverse"]) is not bool:
            raise ValueError("rewrite direction must be boolean")
        if any(type(p) is not int for p in row["position"]):
            raise ValueError("rewrite positions must be integer indices")
        steps.append(RewriteStep(
            row["rule_id"], row["reverse"], tuple(row["position"]),
            tuple((name, parse_term(term)) for name, term in row["binding"]),
            parse_term(row["before"]), parse_term(row["after"])))
    return RewriteCertificate(
        parse_equation(data["goal"]),
        tuple(parse_equation(x) for x in data["assumptions"]),
        tuple(steps), data["rulebook_sha256"])


def horn_certificate_data(certificate) -> dict:
    """Serialize the *existing* Horn certificate without changing its format."""
    def atom(a):
        return {"predicate": a.predicate, "args": list(a.args)}
    return {
        "goal": atom(certificate.goal),
        "assumptions": [atom(a) for a in sorted(certificate.assumptions)],
        "rulebook_sha256": certificate.rulebook_sha256,
        "steps": [{
            "rule_id": edge.rule_id, "binding": [list(pair) for pair in edge.binding],
            "premises": [atom(a) for a in edge.premises],
            "conclusion": atom(edge.conclusion),
        } for edge in certificate.steps],
    }


def verify_problem(data: dict, report: dict) -> bool:
    """External proof replay against a freshly loaded exact problem snapshot."""
    if not isinstance(data, dict) or not isinstance(report, dict):
        return False
    try:
        kind = data.get("logic")
        if kind != report.get("logic") or report.get("certificate") is None:
            return False
        if kind == "equational":
            book, assumptions, goal = load_equational_problem(data)
            cert = load_rewrite_certificate(report["certificate"])
            return verify_rewrite_certificate(book, cert, goal, assumptions)
        if kind == "horn":
            book, assumptions, goal = load_reasoning_problem(data)
            cert = load_certificate(report["certificate"])
            return verify_certificate(book, cert, assumptions, goal)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return False
    return False


def solve_problem(data: dict, *, max_steps: int = 30,
                  max_states: int = 4000, max_edges: int = 10000,
                  max_rounds: int = 100, max_term_nodes: int = 100,
                  iterations: int = 1000, seed: int = 7) -> dict:
    """Return an independently replayed result and explicit trust scope."""
    if not isinstance(data, dict):
        raise ValueError("problem must be a JSON object")
    kind = data.get("logic")
    if kind == "equational":
        book, assumptions, goal = load_equational_problem(data)
        result = prove_equation(book, goal, assumptions=assumptions,
                                max_steps=max_steps, max_states=max_states,
                                max_term_nodes=max_term_nodes)
        cert = result.certificate
        if cert is not None and not verify_rewrite_certificate(book, cert, goal, assumptions):
            raise RuntimeError("equational certificate replay failed")
        return {
            "logic": kind,
            "status": result.status,
            "certificate": certificate_data(cert) if cert else None,
            "certificate_replayed": cert is not None,
            "expanded_states": result.expanded_states,
            "generated_states": result.generated_states,
            "search_depth": result.depth,
            "scope_exhausted": result.scope_exhausted,
            "reviewed_rules": len(book.rules),
            "unverified_candidates": len(book.candidates),
            "trust_scope": "derivability_relative_to_caller_reviewed_equalities_not_Lean_validation",
        }
    if kind == "horn":
        book, facts, goal = load_reasoning_problem(data)
        outcome = derive(book, facts, goal, max_steps=max_steps,
                         iterations=iterations, seed=seed, max_edges=max_edges,
                         max_rounds=max_rounds)
        replayed = outcome.certificate is not None and verify_certificate(
            book, outcome.certificate, facts, goal)
        if outcome.certificate is not None and not replayed:
            raise RuntimeError("Horn certificate replay failed")
        return {
            "logic": kind,
            "status": outcome.status,
            # Retain public Horn certificate format unchanged. Caller can
            # serialize dataclass through its existing dedicated adapter.
            "certificate": horn_certificate_data(outcome.certificate)
                           if outcome.certificate else None,
            "certificate_replayed": replayed,
            "effective_depth": outcome.effective_depth,
            "search_method": outcome.search_method,
            "scope_complete": outcome.scope_complete,
            "reviewed_rules": len(book.rules),
            "unverified_candidates": len(book.candidates),
            "trust_scope": "derivability_relative_to_caller_reviewed_ground_horn_rules",
        }
    raise ValueError("explicit logic selector must be horn or equational")
