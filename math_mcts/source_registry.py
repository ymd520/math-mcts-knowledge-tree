"""Register source-backed mathematical *statements* without inventing importance.

Registered means an imported statement's exact bytes, module, name and immutable
upstream source hash were checked. It does not mean a theorem has been proved
in this run, that the theorem is important, or that its teaching level is known.
Registry can be reproduced from the repository's pinned gz source corpus.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import os
import sqlite3

SOURCE_COMMIT = "54c01c3314d33d15d77893cbe4e0472ff26bb34d"
REGISTRY_SCHEMA = "1"


def register_source_statements(db_path: str | Path,
                               manifest_path: str | Path) -> dict:
    """Register all mechanically checkable imported theorems, reject the rest.

    A GitHub module URL is only a module locator, NOT a theorem-specific line
    citation and not evidence of Lean rerun. Source hash comes from original
    per-statement metadata, independently recomputed from the imported body.
    The caller must have built the index with hash-verified imported shards.
    """
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp = manifest_path.with_name(manifest_path.name + ".building")
    temp.unlink(missing_ok=True)
    accepted = 0
    rejected = Counter()
    seen_hashes = set()
    db = sqlite3.connect(str(db_path))
    try:
        if not db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                          "AND name='metadata'").fetchone():
            raise ValueError("Missing source index metadata")
        if not db.execute("SELECT 1 FROM metadata WHERE key='schema' AND value='1'").fetchone():
            raise ValueError("Unsupported source index schema")
        db.execute("CREATE TABLE IF NOT EXISTS source_registry "
                   "(id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL UNIQUE, "
                   "module TEXT NOT NULL, imported_commit TEXT NOT NULL, "
                   "importance_status TEXT NOT NULL, level INTEGER)")
        # Safety: regenerating must not preserve stale registration entries.
        db.execute("DELETE FROM source_registry")
        with gzip.open(temp, "wt", encoding="utf-8") as out:
            cursor = db.execute("SELECT id, record FROM documents "
                                "WHERE tier='unreviewed_import' ORDER BY id")
            for cid, payload in cursor:
                row = json.loads(payload)
                meta = row.get("original_metadata") or {}
                if meta.get("类型") != "upstream_theorem":
                    rejected["not_upstream_theorem"] += 1
                    continue
                name = row.get("en", "")
                module = row.get("module", "")
                formal = row.get("formal", "")
                fingerprint = meta.get("陈述SHA256", "")
                if not name or not module.startswith("Mathlib.") or not formal:
                    rejected["missing_name_module_or_statement"] += 1
                    continue
                if not formal.startswith("theorem " + name):
                    rejected["unexpected_statement_prefix"] += 1
                    continue
                body = formal.removeprefix("theorem " + name).strip()
                if not body:
                    rejected["empty_theorem_body"] += 1
                    continue
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if not fingerprint or digest != fingerprint:
                    rejected["original_statement_hash_mismatch"] += 1
                    continue
                if digest in seen_hashes:
                    rejected["duplicate_source_statement"] += 1
                    continue
                seen_hashes.add(digest)
                db.execute("INSERT INTO source_registry VALUES (?,?,?,?,?,?)",
                           (cid, digest, module, SOURCE_COMMIT,
                            "unreviewed_importance", None))
                record = {
                    "id": cid,
                    "source": "mathlib4",
                    "module": module,
                    "theorem_name": name,
                    "source_commit": SOURCE_COMMIT,
                    "source_statement_sha256": digest,
                    "registered_statement": True,
                    "reviewed_importance": False,
                    "reviewed_level": None,
                    "proof_verified_this_run": False,
                }
                out.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
                accepted += 1
        total = db.execute("SELECT COUNT(*) FROM documents "
                           "WHERE tier='unreviewed_import'").fetchone()[0]
        if accepted + sum(rejected.values()) != total:
            raise RuntimeError("Registration lost input records")
        db.execute("INSERT OR REPLACE INTO metadata VALUES"
                   "('source_registry_schema', ?)", (REGISTRY_SCHEMA,))
        db.execute("INSERT OR REPLACE INTO metadata VALUES"
                   "('registered_source_count', ?)", (str(accepted),))
        db.execute("INSERT OR REPLACE INTO metadata VALUES"
                   "('registered_source_commit', ?)", (SOURCE_COMMIT,))
        db.commit()
        os.replace(temp, manifest_path)
    except Exception:
        db.rollback()
        temp.unlink(missing_ok=True)
        raise
    finally:
        db.close()
    result = {
        "candidate_count": total,
        "formally_registered_source_statements": accepted,
        "rejected_count": sum(rejected.values()),
        "rejection_reasons": dict(sorted(rejected.items())),
        "mathematical_importance_reviewed_count": 0,
        "level_1_to_4_assigned_count": 0,
        "source_commit": SOURCE_COMMIT,
        "registry_manifest_path": str(manifest_path),
        "status": "registered_source_statements_not_reviewed_importance",
    }
    return result


def get_registered_statement(db_path: str | Path, cid: str) -> dict | None:
    """Retrieve a registered statement without loading the entire source corpus."""
    with sqlite3.connect(str(db_path)) as db:
        row = db.execute(
            "SELECT d.record, r.source_sha256, r.imported_commit "
            "FROM source_registry r JOIN documents d ON d.id=r.id "
            "WHERE r.id=?", (cid,)).fetchone()
    if row is None:
        return None
    original = json.loads(row[0])
    return {
        "id": original["id"],
        "name": original.get("en", ""),
        "formal": original.get("formal", ""),
        "module": original.get("module", ""),
        "source_statement_sha256": row[1],
        "source_commit": row[2],
        "registration_status": "registered",
        "importance_status": "unreviewed",
        "level": None,
    }
