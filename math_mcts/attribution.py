"""Auditable source attribution for imported mathematical knowledge.

The curator of this database is not the discoverer of upstream mathematics.
Module header author names identify credited *file contributors*, NOT
necessarily the original discoverer of every theorem. Never invent a person
or claim the current repository authored imported theorems.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from .source_registry import SOURCE_COMMIT

MATHLIB_URL="https://github.com/leanprover-community/mathlib4"
LICENSE_ID="Apache-2.0"
MODULE_RE=re.compile(r"^Mathlib(?:\.[A-Za-z_][A-Za-z0-9_']*)+$")


def module_source_path(module: str) -> str:
    if not MODULE_RE.fullmatch(module):
        raise ValueError("Invalid Mathlib module; cannot invent a source link")
    return module.replace(".","/")+".lean"


def module_source_url(module: str) -> str:
    return f"{MATHLIB_URL}/blob/{SOURCE_COMMIT}/{module_source_path(module)}"


def parse_file_header(source: str) -> dict:
    """Extract file-level notices only from a supplied pinned source file.

    Author header is not a statement-level provenance claim. No fallback
    author identity is inferred from git account names or module namespaces.
    """
    head=source[:6000]
    block=re.match(r"\s*/-([\s\S]*?)-/",head)
    body=block.group(1) if block else ""
    lines=[x.strip() for x in body.splitlines()]
    credit=next((x[len("Authors:"):].strip() for x in lines
                 if x.startswith("Authors:")), "")
    names=[x.strip() for x in credit.split(",") if x.strip()]
    copyright_notice=next((x for x in lines if x.startswith("Copyright")), "")
    return {"module_header_authors": names,
            "module_header_copyright": copyright_notice,
            "attribution_scope":"module_file_header_not_individual_theorem"}


def source_credit(record: dict, *, tier: str) -> dict:
    """Give a direct, source-specific citation rather than claiming discovery."""
    if tier == "unreviewed_import":
        typ=(record.get("original_metadata") or {}).get("类型","")
        module=str(record.get("module") or "")
        base={
            "knowledge_id":record["id"],
            "knowledge_kind":"upstream_theorem" if typ=="upstream_theorem" else "imported_standard_card",
            "source_project":"mathlib4" if typ=="upstream_theorem" else "imported source archive",
            "source_project_url":MATHLIB_URL if typ=="upstream_theorem" else None,
            "source_commit":SOURCE_COMMIT if typ=="upstream_theorem" else None,
            "source_module":module or None,
            "source_module_url":module_source_url(module) if typ=="upstream_theorem" and MODULE_RE.fullmatch(module) else None,
            "original_theorem_author":"not_individually_identified",
            "file_header_authors":[],
            "license":LICENSE_ID if typ=="upstream_theorem" else "verify_original_source_license",
            "curation_role":"repository maintainers: collection, indexing, metadata and search",
            "mathematics_originality_claim":"none",
            "source_precision":"module_level_only_not_exact_declaration_line",
            "raw_source_file":record.get("import_source_file") or None,
        }
        return base
    return {
        "knowledge_id":record["id"],
        "knowledge_kind":"curated",
        "source_project":None,
        "source_project_url":None,
        "source_commit":None,
        "source_module":record.get("module") or None,
        "source_module_url":record.get("source_url") or record.get("doc_url") or None,
        "original_theorem_author":"not_identified_without_card_source",
        "file_header_authors":[],
        "license":"evaluate_each_original_reference",
        "curation_role":"repository maintainers: compilation and annotations",
        "mathematics_originality_claim":"none",
        "source_precision":"recorded_card_locator" if record.get("source_locator") else "needs_precise_citation",
        "raw_source_file":record.get("import_source_file") or None,
    }


def build_attribution_index(db_path: str | Path) -> dict:
    """Rebuild attribution overlay without modifying mathematical source data."""
    counts=Counter()
    with sqlite3.connect(str(db_path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone():
            raise ValueError("Missing indexed knowledge")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE IF EXISTS knowledge_attribution")
        db.execute("""CREATE TABLE knowledge_attribution (
            id TEXT PRIMARY KEY, source_kind TEXT NOT NULL,
            source_project TEXT, source_module_url TEXT,
            origin_license TEXT NOT NULL,
            attribution_status TEXT NOT NULL,
            data_json TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX attribution_source_kind ON knowledge_attribution(source_kind,id)")
        batch=[]
        for cid,tier,raw in db.execute("SELECT id,tier,record FROM documents ORDER BY id"):
            row=json.loads(raw)
            if row["id"]!=cid:
                raise ValueError("Source ID mismatch in attribution build")
            credit=source_credit(row,tier=tier)
            if tier=="unreviewed_import" and credit["knowledge_kind"]=="upstream_theorem":
                if credit["source_module_url"] is None:
                    raise ValueError("Missing attributable pinned Mathlib module")
            batch.append((cid,credit["knowledge_kind"],credit["source_project"],
                          credit["source_module_url"],credit["license"],
                          credit["source_precision"],
                          json.dumps(credit,ensure_ascii=False,sort_keys=True)))
            counts[credit["knowledge_kind"]]+=1
            if len(batch)==1000:
                db.executemany("INSERT INTO knowledge_attribution VALUES (?,?,?,?,?,?,?)",batch)
                batch=[]
        if batch:
            db.executemany("INSERT INTO knowledge_attribution VALUES (?,?,?,?,?,?,?)",batch)
        db.execute("CREATE INDEX attribution_source_url ON knowledge_attribution(source_module_url)")
        actual=db.execute("SELECT COUNT(*) FROM knowledge_attribution").fetchone()[0]
        expected=db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if expected!=actual: raise RuntimeError("Attribution coverage incomplete")
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('source_attribution_count',?)",(str(actual),))
        db.commit()
    return {"total_attributed_records":actual,
            "by_source_kind":dict(sorted(counts.items())),
            "mathlib_license":LICENSE_ID,
            "mathlib_pinned_commit":SOURCE_COMMIT,
            "warning":"Module citation is not a precise theorem line or its original human discoverer"}


def attribution_by_id(db_path: str | Path, cid: str) -> dict | None:
    with sqlite3.connect(str(db_path)) as db:
        row=db.execute("SELECT data_json FROM knowledge_attribution WHERE id=?",(cid,)).fetchone()
    return json.loads(row[0]) if row else None
