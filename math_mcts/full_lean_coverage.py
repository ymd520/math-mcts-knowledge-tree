"""Truthful global coverage audit of sharded Lean extraction receipts.

A manifest is complete only when every registered ID has an outcome, with no
failed/unrun/unsupported ones and every extracted output anchored to its
batch SHA. No supplied JSON is treated as independent Lean kernel evidence.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
from .source_registry import SOURCE_COMMIT


def audit_full_extraction(plan_file: Path, receipts_root: Path,
                          *, require_complete=False) -> dict:
    plan=json.loads(Path(plan_file).read_text(encoding="utf-8"))
    if plan["mathlib_commit"]!=SOURCE_COMMIT:
        raise ValueError("Plan source commit mismatch")
    expected={b["batch_id"]:b for b in plan["batches"]}
    received={}
    status=Counter()
    resolved=set()
    missing=set()
    receipts=sorted(Path(receipts_root).rglob("*.receipt.json"))
    for path in receipts:
        r=json.loads(path.read_text(encoding="utf-8"))
        bid=r["batch_id"]
        if bid in received:
            raise ValueError("Duplicate batch receipts: "+bid)
        if bid not in expected:
            raise ValueError("Unexpected batch receipt: "+bid)
        b=expected[bid]
        expected_ids={x["source_id"] for x in b["registered_declarations"]}
        if (r["batch_sha256"]!=b["batch_sha256"] or
            r["source_commit"]!=SOURCE_COMMIT or
            set(r["expected_ids"])!=expected_ids):
            raise ValueError("Stale or tampered batch receipt: "+bid)
        exported=set(r["exported_ids"])
        unresolved=set(r["missing_ids"])
        if exported & unresolved or not (exported | unresolved)<=expected_ids:
            raise ValueError("Inconsistent extracted/missing source IDs")
        if r["status"]=="executed":
            if exported | unresolved!=expected_ids:
                raise ValueError("Executed batch has unaccounted source IDs")
            export_file=path.with_name(bid+".jsonl")
            if hashlib.sha256(export_file.read_bytes()).hexdigest()!=r["export_sha256"]:
                raise ValueError("Lean export content hash mismatch")
            actual=[json.loads(line)["source_id"]
                    for line in export_file.read_text(encoding="utf-8").splitlines()]
            if len(actual)!=len(set(actual)) or set(actual)!=exported:
                raise ValueError("Export JSONL does not match its receipt")
            if resolved & exported or missing & unresolved:
                raise ValueError("Duplicate declaration results")
            resolved.update(exported)
            missing.update(unresolved)
        else:
            if exported or unresolved:
                raise ValueError("Failed batch claims successful extracted results")
        received[bid]=r
        status[r["status"]]+=1
    not_run=set(expected)-set(received)
    total=plan["registered_total"]
    planned=plan["scheduled_total"]
    unsupported=plan["unsupported_total"]
    if planned+unsupported!=total:
        raise ValueError("Full-source plan is not exhaustive")
    all_ok=not not_run and not unsupported and not missing and len(resolved)==total and not any(
        k!="executed" for k in status)
    report={
        "registered_total":total,"scheduled_total":planned,
        "unsupported_declarations":unsupported,
        "executed_and_source_exported":len(resolved),
        "lean_missing_declarations":len(missing),
        "not_run_declarations":sum(len(expected[i]["registered_declarations"]) for i in not_run),
        "failed_or_incomplete_declarations":planned-len(resolved)-len(missing)-
            sum(len(expected[i]["registered_declarations"]) for i in not_run),
        "batches_total":len(expected),"batches_with_receipts":len(received),
        "batch_status":dict(status),
        "complete":all_ok,
        "evidence_status":"github_workflow_receipts_plus_untrusted_json_not_independent_proof",
    }
    assert sum(report[k] for k in (
        "unsupported_declarations","executed_and_source_exported",
        "lean_missing_declarations","not_run_declarations",
        "failed_or_incomplete_declarations"))==total
    if require_complete and not all_ok:
        raise RuntimeError("Full 99984 theorem extraction NOT COMPLETE: "+
                           json.dumps(report,sort_keys=True))
    return report
