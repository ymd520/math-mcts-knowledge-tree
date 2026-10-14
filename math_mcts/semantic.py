"""Auditable bridge from knowledge cards to explicitly reviewed Horn rules.

No automatic text-to-logic translation is performed. A human-supplied mapping
must name the card, bind its exact statement snapshot and record mapping review.
This only checks consistency and provenance; it cannot establish rule truth.
"""
from __future__ import annotations

import hashlib
import json

from .reasoning import load_reasoning_problem


def catalog_statement_sha256(concept) -> str:
    """Fingerprint *all* source wording that a rule mapping may depend on."""
    record = {
        "id": concept.id,
        "definition": concept.definition,
        "assumptions": concept.assumptions,
        "conclusion": concept.conclusion,
        "formulas": list(concept.formulas),
        "formal": concept.formal,
        "source_url": concept.source_url,
        "source_locator": concept.source_locator,
        "verification_status": concept.verification_status,
    }
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_catalog_reasoning_problem(data: dict, tree):
    """Return a typed RuleBook, assumptions and goal from reviewed card mappings.

    Uses the same JSON schema as load_reasoning_problem but every rule also needs
    concept_id and concept_sha256. A reviewed rule additionally needs a nonempty
    mapping_review record and explicit source. The review is asserted by the
    caller; this code cannot verify identity, mathematical soundness or novelty.

    Candidate/refuted rules remain inert in the returned RuleBook.
    """
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    seen = set()
    for row in rules:
        concept_id = row.get("concept_id")
        if not isinstance(concept_id, str) or concept_id not in tree.by_id:
            raise ValueError(f"Unknown catalog concept for rule {row.get('id')!r}")
        concept = tree.get(concept_id)
        if row.get("concept_sha256") != catalog_statement_sha256(concept):
            raise ValueError(f"Stale or missing catalog snapshot: {concept_id}")
        if row.get("id") in seen:
            raise ValueError("Duplicate mapped rule id")
        seen.add(row.get("id"))
        if row.get("status") == "reviewed":
            if not row.get("mapping_review", "").strip():
                raise ValueError(f"Reviewed rule lacks mapping review: {row.get('id')}")
            if not row.get("source", "").strip():
                raise ValueError(f"Reviewed rule lacks source: {row.get('id')}")
            if not (concept.definition.strip() or concept.formal.strip()):
                raise ValueError("Cannot review mapping of empty concept statement")
    return load_reasoning_problem(data)
