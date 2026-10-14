"""Deterministic, full-catalog structural and editorial quality audit.

This program does not pretend to certify mathematics. It audits evidence
availability, statement fingerprints, prerequisites and likely duplicates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import re

from .catalog import name_key
from .knowledge import KnowledgeTree


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    concept_ids: tuple[str, ...]
    detail: str


def audit_catalog(tree: KnowledgeTree, sample_limit: int = 30) -> dict:
    """Audit *every* loaded concept, retaining bounded illustrative findings."""
    if sample_limit < 1:
        raise ValueError("sample_limit must be positive")
    totals = Counter()
    examples = defaultdict(list)
    statuses, kinds, levels = Counter(), Counter(), Counter()
    name_groups, statement_groups = defaultdict(list), defaultdict(list)
    verified = set()
    ids = {c.id for c in tree.concepts}

    def record(severity: str, code: str, concept_ids, detail: str):
        totals[code] += 1
        if len(examples[code]) < sample_limit:
            examples[code].append(asdict(Finding(severity, code, tuple(concept_ids), detail)))

    for c in tree.concepts:
        statuses[c.verification_status or "unspecified"] += 1
        kinds[c.kind or "unspecified"] += 1
        levels[str(c.level)] += 1
        if not c.definition.strip() and not c.formal.strip():
            record("error", "empty_statement", [c.id], "No natural or formal statement")
        if not 1 <= c.level <= 5:
            record("error", "invalid_level", [c.id], str(c.level))
        if c.id in verified:
            record("error", "duplicate_id", [c.id], "Non-unique concept identifier")
        verified.add(c.id)
        for prerequisite in c.prereq:
            if prerequisite not in ids:
                record("error", "dangling_prerequisite", [c.id], prerequisite)
            elif prerequisite == c.id:
                record("error", "self_prerequisite", [c.id], prerequisite)
        if len(set(c.prereq)) != len(c.prereq):
            record("warning", "repeated_prerequisite", [c.id], "Repeated prerequisite ID")
        if c.verification_status == "editorial_statement_review_not_formal":
            if not (c.assumptions.strip() and c.conclusion.strip()):
                record("warning", "reviewed_missing_conditions", [c.id],
                       "Editorial statement review lacks explicit assumptions/conclusion")
        if c.source_url and not c.source_url.startswith(("https://", "http://")):
            record("warning", "malformed_source_url", [c.id], c.source_url[:150])
        if not any((c.source_url, c.doc_url, c.import_source_file, c.source_locator)):
            record("info", "missing_source_locator", [c.id], "No directly attributable source")
        if c.statement_sha256:
            if not (c.assumptions and c.conclusion and c.formulas):
                record("warning", "uncheckable_statement_hash", [c.id],
                       "The catalog statement hash requires assumptions, conclusion, formula[0]")
            else:
                digest = hashlib.sha256(
                    (c.assumptions + "\n" + c.conclusion + "\n" + c.formulas[0])
                    .encode("utf-8")).hexdigest()
                if digest != c.statement_sha256:
                    record("error", "statement_hash_mismatch", [c.id],
                           "Statement snapshot does not match declared SHA256")
        if c.cn:
            name_groups[name_key(c.cn)].append(c)
        if c.definition.strip():
            # Potential exact duplicates, not proof of mathematical equivalence.
            statement_groups[(name_key(c.definition), c.kind)].append(c)

    for key, concepts in name_groups.items():
        if len(concepts) > 1:
            record("info", "homonymous_name", [c.id for c in concepts],
                   f"Shared normalized Chinese name: {concepts[0].cn}")
    for concepts in statement_groups.values():
        if len(concepts) > 1:
            record("warning", "identical_statement_candidates",
                   [c.id for c in concepts], "Same normalized definition and kind")

    # Reuse authoritative integrity validation to check cycle detection.
    for issue in tree.check_integrity():
        if issue.startswith("环:"):
            record("error", "prerequisite_cycle", [], issue)

    return {
        "scope": "structural_and_editorial_only_not_mathematical_certification",
        "scanned": len(tree.concepts),
        "metadata": {"statuses": dict(statuses), "kinds": dict(kinds),
                     "levels": dict(levels)},
        "counts": dict(sorted(totals.items())),
        "examples": dict(examples),
        "fatal_count": sum(count for code, count in totals.items()
                           if code in {"empty_statement", "invalid_level",
                                       "duplicate_id", "dangling_prerequisite",
                                       "self_prerequisite", "statement_hash_mismatch",
                                       "prerequisite_cycle"}),
    }


def main():
    parser = argparse.ArgumentParser(description="Audit loaded math MCTS knowledge")
    parser.add_argument("-o", "--output", default="catalog_audit.json")
    parser.add_argument("--sample-limit", type=int, default=30)
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args()
    result = audit_catalog(KnowledgeTree.load(), args.sample_limit)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"scanned": result["scanned"], "counts": result["counts"],
                      "fatal_count": result["fatal_count"]}, ensure_ascii=False))
    if args.fail_on_errors and result["fatal_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
