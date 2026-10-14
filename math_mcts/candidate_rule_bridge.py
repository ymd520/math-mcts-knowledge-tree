"""Fail-closed bridge from external mathematical text to typed candidate rules.

An explicit human-authored translation of a source statement into a ground or
function-free Horn clause is a *hypothesis*, not a proof that the translation
faithfully represents the source, and not a formal source verification.
The returned rules always have status='candidate'; RuleBook cannot apply them.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import sqlite3

from .reasoning import Atom, Rule, RuleBook


def _atom(item: object) -> Atom:
    if not isinstance(item, dict) or not isinstance(item.get("predicate"), str):
        raise ValueError("Typed atom must have a predicate")
    args = item.get("args", [])
    if not isinstance(args, list) or any(not isinstance(x, str) for x in args):
        raise ValueError("Typed atom arguments must be a list of strings")
    return Atom(item["predicate"], tuple(args))


def candidate_rules(db_path: str | Path, mappings: list[dict],
                    signatures: Mapping[str, tuple[str, ...]],
                    objects: Mapping[str, str]) -> tuple[Rule, ...]:
    if not isinstance(mappings, list) or len(mappings) > 10000:
        raise ValueError("Expected at most 10000 explicit candidate translations")
    result = []
    identifiers = set()
    with sqlite3.connect(str(db_path)) as db:
        for m in mappings:
            if not isinstance(m, dict):
                raise ValueError("Invalid candidate translation")
            if m.get("status", "candidate") != "candidate":
                raise ValueError("External translation cannot self-promote to reviewed rule")
            cid = m.get("candidate_id")
            digest = m.get("statement_sha256")
            if not isinstance(cid, str) or not isinstance(digest, str):
                raise ValueError("Candidate ID and source statement SHA are required")
            hit = db.execute("SELECT record FROM external_candidates WHERE id=?", (cid,)).fetchone()
            if not hit:
                raise ValueError("External candidate is not present: " + cid)
            source = json.loads(hit[0])
            if source["statement_sha256"] != digest:
                raise ValueError("Stale or tampered source statement fingerprint")
            if source["kind"] not in {"theorem", "lemma"}:
                raise ValueError("Only source theorem/lemma may be mapped to rule candidates")
            variables = m.get("variables", {})
            if not isinstance(variables, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in variables.items()
            ):
                raise ValueError("Variables must be sort declarations")
            premises = m.get("premises")
            if not isinstance(premises, list):
                raise ValueError("An explicit premises list is required")
            rule_id = "unreviewed_" + cid
            if rule_id in identifiers:
                raise ValueError("Duplicate candidate mapping")
            identifiers.add(rule_id)
            rule = Rule(rule_id, tuple(_atom(p) for p in premises),
                        _atom(m.get("conclusion")),
                        tuple(sorted(variables.items())),
                        source=source["source_url"] + "#" + source["locator"] +
                               " @ " + source["source_ref"],
                        status="candidate",
                        concept_id=cid,
                        concept_sha256=digest,
                        mapping_review="")
            result.append(rule)
    # Independent typed RuleBook construction checks sorts, variable binding,
    # predicate arities, duplicate rule identifiers. Candidate status is locked.
    book = RuleBook(signatures, objects, result)
    if book.rules or len(book.candidates) != len(result):
        raise RuntimeError("External proposal leaked into the reviewed rule layer")
    return tuple(result)


def bridge_report(db_path: str | Path, spec_path: str | Path) -> dict:
    data = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Bridge specification must be a JSON object")
    rules = candidate_rules(db_path, data["candidates"],
                            data["signatures"], data["objects"])
    return {"candidate_rule_count": len(rules),
            "active_reviewed_rules": 0,
            "source_statements_kernel_verified": 0,
            "semantic_translation_verified": False,
            "typed_candidates": [{"rule_id": r.id, "source_id": r.concept_id,
                                   "statement_sha256": r.concept_sha256,
                                   "premise_count": len(r.premises),
                                   "conclusion_predicate": r.conclusion.predicate,
                                   "status": r.status}
                                  for r in rules],
            "status": "typed_translations_are_untrusted_non_executable_candidates"}
