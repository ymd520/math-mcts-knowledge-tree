"""Audited level 1–4 expansion targets. Candidates are not curated entries."""
from __future__ import annotations
import json
from pathlib import Path

from .knowledge import KnowledgeTree

TARGET_TOTAL = 100000
TARGET_LEVEL = {1: 25000, 2: 25000, 3: 25000, 4: 25000}


def expansion_status(tree: KnowledgeTree, *, unreviewed_candidates: int = 0) -> dict:
    counts = tree.inventory()["important_levels"]
    current = {i: counts.get(i, 0) for i in TARGET_LEVEL}
    gap = {i: max(0, goal - current[i]) for i, goal in TARGET_LEVEL.items()}
    return {
        "target_total": TARGET_TOTAL,
        "targets": {str(k): v for k, v in TARGET_LEVEL.items()},
        "curated_important": {str(k): v for k, v in current.items()},
        "gaps": {str(k): v for k, v in gap.items()},
        "verified_target_progress": sum(current.values()),
        "remaining": sum(gap.values()),
        "unreviewed_search_candidates": unreviewed_candidates,
        "warning": (
            "Imported mathlib level=5 denotes ungraded; indexed candidates "
            "have no promoted importance or grade. Named source presence and "
            "Lean-shaped text do not prove importance or actual correctness."
        ),
    }


def write_status(path: str | Path, tree: KnowledgeTree,
                 unreviewed_candidates: int = 0) -> dict:
    report = expansion_status(tree, unreviewed_candidates=unreviewed_candidates)
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return report
