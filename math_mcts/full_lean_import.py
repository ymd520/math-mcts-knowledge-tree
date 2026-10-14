"""Incremental full-corpus Lean result importer, retaining provenance.

Importing any JSON is NEVER sufficient to claim Lean kernel verification.
All records remain externally unattested even if a CI run ID is reported.
Original source hash/module/declaration and batch fingerprints are checked;
successful existing data is never erased by importing a partial shard.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
from .source_registry import SOURCE_COMMIT
from .lean_reference_index import _match_source

HEADS={"forallE","app","sort","const","other","unreported"}


def _refs(raw):
    if not isinstance(raw,list) or len(raw)>20000:
        raise ValueError("Malformed Lean dependency references")
    if any(not isinstance(x,str) or not x or len(x)>1024 or
           any(ord(c)<32 for c in x) for x in raw):
        raise ValueError("Malformed/unsafe Lean constant name")
    if len(set(raw)) != len(raw):
        raise ValueError("Duplicated Lean constant reference")
    return sorted(raw)


def ingest_full_receipts(db_path: str | Path, plan_file: str | Path,
                         root: str | Path) -> dict:
    """Idempotently import completed batches, even when other batches failed."""
    plan=json.loads(Path(plan_file).read_text(encoding="utf-8"))
    if plan["mathlib_commit"]!=SOURCE_COMMIT:
        raise ValueError("Wrong upstream source commit")
    batches={b["batch_id"]:b for b in plan["batches"]}
    from .full_lean_coverage import audit_full_extraction
    coverage=audit_full_extraction(Path(plan_file),Path(root))
    inserted=0
    repeated=0
    with sqlite3.connect(str(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        required={"documents","source_registry","classified_knowledge","metadata"}
        actual={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required<=actual: raise ValueError("Source registry and classification required")
        db.execute("""CREATE TABLE IF NOT EXISTS lean_full_declarations (
            id TEXT PRIMARY KEY, module TEXT NOT NULL,
            source_sha256 TEXT NOT NULL, declaration TEXT NOT NULL,
            type_sha256 TEXT NOT NULL, type_expression TEXT NOT NULL,
            leading_pi_binders INTEGER,
            elaborated_type_head TEXT NOT NULL, evidence_status TEXT NOT NULL,
            github_run_id TEXT NOT NULL, batch_id TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS lean_full_references (
            id TEXT NOT NULL, referenced_constant TEXT NOT NULL,
            reference_kind TEXT NOT NULL,
            PRIMARY KEY(id, referenced_constant, reference_kind)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS lean_full_ref_reverse "
                   "ON lean_full_references(referenced_constant,reference_kind,id)")
        db.execute("CREATE INDEX IF NOT EXISTS lean_full_module "
                   "ON lean_full_declarations(module,id)")
        for path in sorted(Path(root).rglob("*.receipt.json")):
            receipt=json.loads(path.read_text())
            if receipt.get("status")!="executed": continue
            batch=batches[receipt["batch_id"]]
            requested={r["source_id"]:r for r in batch["registered_declarations"]}
            export=path.with_name(receipt["batch_id"]+".jsonl")
            for line in export.read_text(encoding="utf-8").splitlines():
                obj=json.loads(line)
                cid=obj["source_id"]
                if cid not in requested or obj.get("source_statement_sha256")!=requested[cid]["source_statement_sha256"]:
                    raise ValueError("Wrong source declaration batch or fingerprint")
                if obj.get("module")!=batch["module"] or obj.get("mathlib_commit")!=SOURCE_COMMIT:
                    raise ValueError("Wrong source module or mathlib commit")
                sha=_match_source(db,obj)
                typ=str(obj.get("type_expression",""))
                if not typ or len(typ)>300000: raise ValueError("Invalid elaborated type")
                binder=obj.get("leading_pi_binders")
                if binder is not None and (type(binder)!=int or not 0<=binder<=10000):
                    raise ValueError("Invalid Lean Pi binder count")
                head=obj.get("elaborated_type_head","unreported")
                if head not in HEADS:
                    raise ValueError("Invalid Lean type constructor tag")
                type_sha=hashlib.sha256(typ.encode()).hexdigest()
                row=(cid,batch["module"],sha,obj["declaration"],type_sha,typ,
                     binder,head,"external_export_unattested",
                     str(receipt.get("github_run_id","unattested_external")),
                     receipt["batch_id"])
                existing=db.execute("SELECT source_sha256,type_sha256,leading_pi_binders,"
                    "elaborated_type_head FROM lean_full_declarations WHERE id=?",(cid,)).fetchone()
                if existing:
                    if existing!=(sha,type_sha,binder,head):
                        raise ValueError("Conflicting full Lean extraction re-import")
                    repeated+=1
                    continue
                db.execute("INSERT INTO lean_full_declarations VALUES (?,?,?,?,?,?,?,?,?,?,?)",row)
                for kind,keys in (("type_constant",_refs(obj["type_references"])),
                                  ("proof_term_constant",_refs(obj["proof_references"]))):
                    db.executemany("INSERT INTO lean_full_references VALUES(?,?,?)",
                                   [(cid,r,kind) for r in keys])
                inserted+=1
        stored=db.execute("SELECT COUNT(*) FROM lean_full_declarations").fetchone()[0]
        if stored>plan["registered_total"]:
            raise ValueError("More extracted declarations than registered source")
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('lean_full_stored_count',?)",(str(stored),))
        db.commit()
    return {"new_source_matched_entries":inserted,"idempotent_entries":repeated,
            "total_stored_entries":stored,
            "registered_total":plan["registered_total"],
            "reviewed_math_implications":0,
            "evidence_status":"external_export_unattested",
            "receipt_coverage":coverage}


def indexed_type_conditions(db_path: str | Path, cid: str) -> dict:
    """Structural hints, NOT hypotheses/quantifier logical rule inference."""
    with sqlite3.connect(str(db_path)) as db:
        row=db.execute("""SELECT declaration,type_expression,leading_pi_binders,
              elaborated_type_head,source_sha256,evidence_status
              FROM lean_full_declarations WHERE id=?""",(cid,)).fetchone()
        if row is None: raise KeyError(cid)
        edges=db.execute("""SELECT referenced_constant,reference_kind
             FROM lean_full_references WHERE id=?
             ORDER BY reference_kind,referenced_constant""",(cid,)).fetchall()
    return {"source_id":cid,"declaration":row[0],"type_expression":row[1],
            "leading_pi_binders":row[2],"elaborated_type_head":row[3],
            "source_statement_sha256":row[4],"evidence_status":row[5],
            "type_or_proof_references":[{"name":a,"kind":b} for a,b in edges],
            "logical_assumptions_verified":False,
            "usable_as_horn_rule":False,
            "reason":"Pi binders include implicit types, instances and quantifiers; "
                     "constant references alone do not prove implication"}
