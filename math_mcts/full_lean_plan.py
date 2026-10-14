"""Exhaustive, source-pinned mathlib theorem extraction work manifest.

A plan covers EVERY registered theorem, including declarations whose names
cannot yet be rendered safely as Lean syntax. Those are explicit exceptions,
not silently dropped; having a workplan is not having run Lean.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import sqlite3

from .source_registry import SOURCE_COMMIT
from .attribution import module_source_path

_NAME = re.compile(r"^[^\s\x00-\x1f\x7f.]+(?:\.[^\s\x00-\x1f\x7f.]+)*$")


def build_full_plan(db_path: str | Path, output_path: str | Path,
                    *, max_per_batch: int = 60) -> dict:
    if not 1 <= max_per_batch <= 200:
        raise ValueError("Batch must have 1..200 declarations")
    modules = defaultdict(list)
    excluded = []
    seen = set()
    with sqlite3.connect(str(db_path)) as db:
        rows = db.execute("""SELECT r.id, r.module, r.source_sha256,
                                    r.imported_commit, d.record
                  FROM source_registry r JOIN documents d ON r.id=d.id
                  ORDER BY r.module, r.id""")
        for cid, module, sha, commit, payload in rows:
            if cid in seen:
                raise ValueError("Duplicate registered source theorem ID")
            seen.add(cid)
            row = json.loads(payload)
            if row.get("id") != cid or row.get("module") != module:
                raise ValueError("Source registry and document mismatch")
            if commit != SOURCE_COMMIT:
                raise ValueError("Registry contains a different mathlib commit")
            name = str(row.get("en") or "")
            formal = str(row.get("formal") or "")
            prefix = "theorem " + name
            if not formal.startswith(prefix) or hashlib.sha256(
                    formal[len(prefix):].strip().encode()).hexdigest() != sha:
                raise ValueError("Stale or corrupted theorem source")
            try:
                module_source_path(module)
            except ValueError:
                excluded.append({"id": cid, "module": module,
                                 "reason": "unsupported_module_locator"})
                continue
            if not _NAME.fullmatch(name):
                excluded.append({"id": cid, "module": module,
                                 "reason": "unsupported_declaration_syntax"})
                continue
            modules[module].append({"source_id": cid, "declaration": name,
                                    "source_statement_sha256": sha})
        registered = db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
    if len(seen) != registered:
        raise RuntimeError("Plan did not visit all source registry rows")
    batches = []
    for module in sorted(modules):
        records = modules[module]
        for i in range(0, len(records), max_per_batch):
            part = records[i:i + max_per_batch]
            k = len(batches)
            batches.append({
                "batch_id": f"B{k:06d}", "module": module,
                "module_path": module_source_path(module),
                "registered_declarations": part,
                "batch_sha256": hashlib.sha256(json.dumps(
                    part, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(),
            })
    scheduled = sum(len(x["registered_declarations"]) for x in batches)
    if scheduled + len(excluded) != registered:
        raise RuntimeError("Missing registered theorem from full extraction plan")
    plan = {
        "schema": 1, "mathlib_commit": SOURCE_COMMIT,
        "registered_total": registered, "scheduled_total": scheduled,
        "unsupported_total": len(excluded),
        "batch_limit": max_per_batch, "module_count": len(modules),
        "batch_count": len(batches), "batches": batches,
        "unsupported": excluded,
        "execution_status": "not_executed",
        "proof_status": "source_records_only_not_lean_kernel_checks",
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False,
                                 sort_keys=True, indent=2) + "\n")
    return {
        k: v for k, v in plan.items() if k not in {"batches", "unsupported"}
    } | {"reason_counts": dict(Counter(x["reason"] for x in excluded)),
         "manifest_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def partition_batches(plan: dict, *, worker: int, workers: int) -> list[dict]:
    """Partition complete batch set; no partial sample or hidden omission."""
    if not 1 <= workers <= 256 or not 0 <= worker < workers:
        raise ValueError("Invalid worker partition")
    return [batch for i, batch in enumerate(plan["batches"])
            if i % workers == worker]
