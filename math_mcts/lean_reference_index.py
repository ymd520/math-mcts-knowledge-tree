"""Version-locked ingestion of actual Lean elaborated declaration *references*.

Data is produced by a Lean environment exporter (see lean/ExtractCoreSmoke.lean).
The importer strictly joins it to original registered source statements.
It does not infer mathematical implications from names, dependencies or types;
these are syntactic relationships from elaborated Lean terms only.

Records imported without an independently run Lean extractor remain
'external_export_unattested' and are NEVER reviewed Horn rules/proofs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
from collections import Counter, deque

from .source_registry import SOURCE_COMMIT

SCHEMA = "1"
NAME = re.compile(r"^[A-Za-z_][A-Za-z_0-9'.]*(?:\.[A-Za-z_0-9']+)*$")
MAX_RECORD_BYTES = 1_000_000
MAX_REFS = 20_000


def _validated_references(raw, decl):
    if not isinstance(raw, list) or len(raw) > MAX_REFS:
        raise ValueError("Invalid Lean references list")
    if any(not isinstance(n, str) or not NAME.fullmatch(n) for n in raw):
        raise ValueError("Invalid Lean constant name")
    if len(set(raw)) != len(raw):
        raise ValueError("Duplicate Lean references")
    return sorted(n for n in raw if n != decl)


def _match_source(db, record):
    source_id = record["source_id"]
    found = db.execute("""SELECT d.record,r.source_sha256,r.imported_commit
          FROM documents d JOIN source_registry r ON d.id=r.id
          WHERE r.id=?""", (source_id,)).fetchone()
    if not found:
        raise ValueError(f"Unknown registered source ID: {source_id}")
    source, digest, commit = found
    row = json.loads(source)
    module = record["module"]
    if module != row.get("module") or commit != SOURCE_COMMIT:
        raise ValueError("Mathlib module or source commit mismatch")
    name = record["declaration"]
    short = str(row.get("en") or "")
    if not (name == short or name.endswith("." + short)):
        raise ValueError(f"Lean declaration does not match source theorem: {source_id}")
    statement = str(row.get("formal") or "")
    prefix = "theorem " + short
    if not statement.startswith(prefix):
        raise ValueError("Malformed source theorem")
    verified = hashlib.sha256(statement[len(prefix):].strip().encode()).hexdigest()
    if verified != digest or record["source_statement_sha256"] != digest:
        raise ValueError("Source theorem changed or mismatched SHA256")
    return digest


def import_lean_exports(db_path: str | Path, jsonl_path: str | Path,
                        *, expected_mathlib_commit: str = SOURCE_COMMIT) -> dict:
    """Import source-checked real-export *claims*, never certify untrusted input.

    An untrusted JSONL can lie about extraction. The provenance label remains
    external_export_unattested until an independently executed Lean workflow
    supplies verifiable run evidence. CLI testing can validate integrity, not
    Lean's kernel from JSON alone. Import is transactional.
    """
    if expected_mathlib_commit != SOURCE_COMMIT:
        raise ValueError("Pinned mathlib commit must match the source registry")
    path = Path(jsonl_path)
    source_bytes = path.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    if not source_bytes:
        raise ValueError("Empty Lean export")
    records = []
    for line in source_bytes.splitlines():
        if len(line) > MAX_RECORD_BYTES:
            raise ValueError("Oversized export record")
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError("Lean export must consist of JSON objects")
        required = ("source_id","declaration","module","mathlib_commit",
                    "source_statement_sha256","type_expression",
                    "type_references","proof_references","lean_version")
        if any(k not in obj for k in required):
            raise ValueError("Missing mandatory Lean export field")
        for k in ("source_id","declaration","module","mathlib_commit",
                  "source_statement_sha256","type_expression","lean_version"):
            if not isinstance(obj[k], str) or not obj[k].strip():
                raise ValueError(f"Invalid field: {k}")
        if (obj["mathlib_commit"] != SOURCE_COMMIT or
                not NAME.fullmatch(obj["declaration"]) or
                not NAME.fullmatch(obj["module"]) or
                len(obj["type_expression"]) > 300000):
            raise ValueError("Invalid or stale Lean export source identity")
        typerefs = _validated_references(obj["type_references"], obj["declaration"])
        proofrefs = _validated_references(obj["proof_references"], obj["declaration"])
        records.append((obj, typerefs, proofrefs))
    ids = [obj["source_id"] for obj, _, _ in records]
    names = [obj["declaration"] for obj, _, _ in records]
    if len(set(ids)) != len(ids) or len(set(names)) != len(names):
        raise ValueError("Duplicate export ID or fully qualified theorem name")

    with sqlite3.connect(str(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        required = {"documents", "source_registry", "classified_knowledge", "metadata"}
        existing = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= existing:
            raise ValueError("Build source index, register and classify first")
        db.execute("DROP TABLE IF EXISTS lean_dependency_edges")
        db.execute("DROP TABLE IF EXISTS lean_declaration_export")
        db.execute("""CREATE TABLE lean_declaration_export (
            id TEXT PRIMARY KEY,
            declaration TEXT NOT NULL UNIQUE,
            source_module TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            type_sha256 TEXT NOT NULL,
            type_expression TEXT NOT NULL,
            lean_version TEXT NOT NULL,
            evidence_status TEXT NOT NULL,
            export_file_sha256 TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE lean_dependency_edges (
            declaration_id TEXT NOT NULL,
            referenced_constant TEXT NOT NULL,
            relation TEXT NOT NULL,
            PRIMARY KEY(declaration_id, referenced_constant, relation)
        )""")
        db.execute("CREATE INDEX lean_edge_incoming ON "
                   "lean_dependency_edges(referenced_constant,relation,declaration_id)")
        db.execute("CREATE INDEX lean_export_module ON "
                   "lean_declaration_export(source_module,id)")
        counts = Counter()
        for obj, type_refs, proof_refs in records:
            source_sha = _match_source(db, obj)
            type_sha = hashlib.sha256(obj["type_expression"].encode()).hexdigest()
            db.execute("INSERT INTO lean_declaration_export VALUES(?,?,?,?,?,?,?,?,?)",
                       (obj["source_id"], obj["declaration"], obj["module"],
                        source_sha, type_sha, obj["type_expression"],
                        obj["lean_version"], "external_export_unattested", digest))
            for relation, refs in (("elaborated_type_reference", type_refs),
                                   ("elaborated_proof_term_reference", proof_refs)):
                db.executemany("INSERT INTO lean_dependency_edges VALUES (?,?,?)",
                               [(obj["source_id"], x, relation) for x in refs])
                counts[relation] += len(refs)
        db.execute("INSERT OR REPLACE INTO metadata VALUES('lean_export_schema', ?)",
                   (SCHEMA,))
        db.execute("INSERT OR REPLACE INTO metadata VALUES('lean_export_sha256', ?)",
                   (digest,))
        db.execute("INSERT OR REPLACE INTO metadata VALUES('lean_export_count', ?)",
                   (str(len(records)),))
        db.commit()
        catalog_count = db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
    return {"matched_registered_theorems": len(records),
            "registered_theorems_total": catalog_count,
            "unmatched_registered_theorems": catalog_count - len(records),
            "export_file_sha256": digest, "edges": dict(counts),
            "evidence_status": "external_export_unattested",
            "warning": "Json alone cannot certify genuine Lean execution or theorem truth"}


class LeanReferenceGraph:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with sqlite3.connect(self.db_path) as db:
            if not db.execute("SELECT name FROM sqlite_master WHERE "
                              "name='lean_declaration_export'").fetchone():
                raise ValueError("No Lean exports imported")

    def references(self, source_id: str, *, relation: str | None = None,
                   limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be 1..1000")
        if relation not in (None,"elaborated_type_reference",
                            "elaborated_proof_term_reference"):
            raise ValueError("Unknown reference type")
        with sqlite3.connect(self.db_path) as db:
            sql = ("SELECT referenced_constant,relation FROM lean_dependency_edges "
                   "WHERE declaration_id=?")
            params: list = [source_id]
            if relation:
                sql += " AND relation=?"
                params.append(relation)
            sql += " ORDER BY relation,referenced_constant LIMIT ?"
            params.append(limit)
            return [{"constant": n, "relation": kind,
                     "status": "syntactic_reference_not_inference"}
                    for n,kind in db.execute(sql,params)]

    def backward_dependencies(self, source_id: str, *, max_hops: int = 4,
                              max_nodes: int = 500) -> dict:
        """Explore exact *referenced* exported constants, not inferred theorems."""
        if max_hops < 0 or not 1 <= max_nodes <= 10000:
            raise ValueError("Invalid dependency bounds")
        with sqlite3.connect(self.db_path) as db:
            root = db.execute("SELECT declaration FROM lean_declaration_export "
                              "WHERE id=?", (source_id,)).fetchone()
            if root is None:
                raise KeyError(source_id)
            seen = {source_id}
            queue = deque([(source_id,0)])
            edges = []
            while queue:
                current, depth = queue.popleft()
                if depth >= max_hops:
                    continue
                rows = db.execute("""SELECT dep.id, e.relation
                    FROM lean_dependency_edges e
                    JOIN lean_declaration_export dep
                    ON dep.declaration=e.referenced_constant
                    WHERE e.declaration_id=?
                    ORDER BY dep.id,e.relation""",(current,)).fetchall()
                for neighbor,relation in rows:
                    edges.append({"dependent":current,"dependency":neighbor,
                                  "relation":relation,"status":"syntactic_only"})
                    if neighbor not in seen and len(seen)<max_nodes:
                        seen.add(neighbor)
                        queue.append((neighbor,depth+1))
            return {"root":source_id,"reachable_declarations":len(seen),
                    "references":edges,"complete_within_node_cap":len(seen)<max_nodes,
                    "warning":"References are not derivation steps"}
