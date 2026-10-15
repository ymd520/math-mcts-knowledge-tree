"""Append-only, source-aware external mathematics candidate store.

This is a candidate/evidence layer, not the curated catalog or a proof system.
No row imported by this module receives a verified, important, or level label.
The store lives in a separate SQLite DB so rebuilding math_index.sqlite cannot
silently delete a different source collection. Standard library only.
"""
from __future__ import annotations

from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import urlparse

from .fast_index import terms_for

KINDS = frozenset({"theorem", "lemma", "definition", "method", "conjecture",
                   "counterexample", "paper", "excerpt", "review"})
FIELDS = ("source", "source_ref", "source_url", "license", "locator",
          "name", "kind", "statement")
SCHEMA = "1"
OPTIONAL = ("domain", "branch", "assumptions", "conclusion", "formula",
            "proof_hint", "counterexample_hint", "source_provider", "provider_url",
            "paper_title", "authors", "original_source", "original_kind",
            "external_id", "source_precision", "reuse_policy", "doi")
_MAX_LINE = 100_000
_MAX_STATEMENT = 12_000
_SPACE = re.compile(r"\s+")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_statement(statement: str) -> str:
    # This gives lexical duplicate *leads*. It proves no equivalence.
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", statement)).strip()


def _validate(record: object) -> dict:
    if not isinstance(record, dict):
        raise ValueError("Source record must be a JSON object")
    row = {}
    for field in FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Missing nonempty text field: " + field)
        if len(value) > (_MAX_STATEMENT if field == "statement" else 1000):
            raise ValueError("Field too large: " + field)
        row[field] = value.strip()
    for field in OPTIONAL:
        if field in record:
            value = record[field]
            if not isinstance(value, str) or len(value) > _MAX_STATEMENT:
                raise ValueError("Invalid optional note: " + field)
            row[field] = value.strip()
    if row["source_ref"].casefold() in {"main", "master", "head", "latest"}:
        raise ValueError("Use a pinned source_ref rather than a moving branch")
    if row["kind"] not in KINDS:
        raise ValueError("Unsupported mathematical record kind")
    u = urlparse(row["source_url"])
    if u.scheme != "https" or not u.netloc or u.username or u.password:
        raise ValueError("source_url must be an HTTPS locator without credentials")
    if len(row["statement"]) < 8:
        raise ValueError("Statement is too short to review")
    # Identity tracks a declaration *at an immutable or explicitly named ref*.
    # Source versions must not silently overwrite one another.
    key = json.dumps([row["source"], row["source_ref"], row["locator"]],
                     separators=(",", ":"), ensure_ascii=False)
    row["id"] = "EXT_" + _digest(key)[:32]
    row["statement_sha256"] = _digest(row["statement"])
    row["normalized_statement_sha256"] = _digest(_canonical_statement(row["statement"]))
    row["curation_status"] = "unreviewed_external_source"
    row["difficulty_level"] = None
    row["importance_status"] = "unrated"
    row["proof_verified_this_run"] = False
    row["license_verified"] = False
    return row


def _connect(db_path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_path))
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS external_candidates(
        id TEXT PRIMARY KEY, source TEXT NOT NULL, source_ref TEXT NOT NULL,
        locator TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
        statement_sha256 TEXT NOT NULL, normalized_statement_sha256 TEXT NOT NULL,
        record TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS ec_source ON external_candidates(source, source_ref)")
    db.execute("CREATE INDEX IF NOT EXISTS ec_normalized ON external_candidates(normalized_statement_sha256)")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS external_terms USING fts5(terms, tokenize='unicode61')")
    db.execute("CREATE TABLE IF NOT EXISTS expansion_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO expansion_metadata VALUES('schema', ?)", (SCHEMA,))
    if db.execute("SELECT value FROM expansion_metadata WHERE key='schema'").fetchone()[0] != SCHEMA:
        db.close()
        raise ValueError("Unsupported expansion schema")
    db.commit()
    return db


def import_jsonl(db_path: str | Path, input_path: str | Path, *, max_records: int = 1000000) -> dict:
    """Import a manifest of *locally provided* JSONL or JSONL.gz entries.

    Idempotent. Reusing the same source/ref/locator with changed text rejects
    the entire transaction; changed upstream material needs a distinct ref.
    No content is fetched or copied from a third-party website by this code.
    """
    if max_records < 1:
        raise ValueError("max_records must be positive")
    path = Path(input_path)
    opener = gzip.open if path.suffix == ".gz" else open
    db = _connect(db_path)
    inserted = 0
    same = 0
    processed = 0
    try:
        db.execute("BEGIN IMMEDIATE")
        with opener(path, "rt", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if len(line) > _MAX_LINE:
                    raise ValueError(f"Line {line_no}: exceeds maximum size")
                if not line.strip():
                    continue
                processed += 1
                if processed > max_records:
                    raise ValueError("Input exceeds max_records")
                try:
                    row = _validate(json.loads(line))
                except (ValueError, TypeError, json.JSONDecodeError) as e:
                    raise ValueError(f"Line {line_no}: {e}") from e
                old = db.execute("SELECT record FROM external_candidates WHERE id=?",
                                 (row["id"],)).fetchone()
                if old:
                    if json.loads(old[0]) != row:
                        raise ValueError(f"Line {line_no}: same locator/ref has changed")
                    same += 1
                    continue
                payload = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                db.execute("INSERT INTO external_candidates VALUES(?,?,?,?,?,?,?,?,?)",
                           (row["id"], row["source"], row["source_ref"],
                            row["locator"], row["kind"], row["name"],
                            row["statement_sha256"], row["normalized_statement_sha256"],
                            payload))
                rid = db.execute("SELECT rowid FROM external_candidates WHERE id=?",
                                 (row["id"],)).fetchone()[0]
                searchable = " ".join([row["source"], row["name"], row["kind"],
                                       row["statement"], row["locator"],
                                       *(row.get(f, "") for f in OPTIONAL)])
                db.execute("INSERT INTO external_terms(rowid,terms) VALUES(?,?)",
                           (rid, " ".join(terms_for(searchable))))
                inserted += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"input_records": processed, "inserted": inserted,
            "already_present_identical": same, "new_curated": 0,
            "verified_proofs_this_run": 0, "status": "external_candidates_unreviewed"}


def _fts_query(query: str) -> str:
    terms = terms_for(query)[:24]
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)


def search(db_path: str | Path, query: str, *, limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be in [1,1000]")
    expression = _fts_query(query)
    if not expression:
        return []
    with closing(_connect(db_path)) as db:
        rows = db.execute("""SELECT e.record,
            (SELECT COUNT(*) FROM external_candidates d
             WHERE d.normalized_statement_sha256=e.normalized_statement_sha256) AS same_text
            FROM external_terms f JOIN external_candidates e ON e.rowid=f.rowid
            WHERE external_terms MATCH ? ORDER BY bm25(external_terms), e.id LIMIT ?""",
            (expression, limit)).fetchall()
    return [{**json.loads(blob), "same_normalized_text_count": count,
             "same_text_means_equivalent": False} for blob, count in rows]


def inventory(db_path: str | Path) -> dict:
    with _connect(db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM external_candidates").fetchone()[0]
        by_source = dict(db.execute(
            "SELECT source, COUNT(*) FROM external_candidates GROUP BY source ORDER BY source"))
        by_kind = dict(db.execute(
            "SELECT kind, COUNT(*) FROM external_candidates GROUP BY kind ORDER BY kind"))
        repeated = db.execute("""SELECT COUNT(*) FROM (
          SELECT normalized_statement_sha256 FROM external_candidates
          GROUP BY normalized_statement_sha256 HAVING COUNT(*) > 1)""").fetchone()[0]
    return {"external_candidates": count, "by_source": by_source,
            "by_kind": by_kind, "lexical_duplicate_groups": repeated,
            "reviewed_important_from_import": 0, "reviewed_level_from_import": 0,
            "proofs_verified_from_import": 0}


def mathlib_review_snapshot(db_path: str | Path) -> dict:
    """Read the existing index without attributing editorial review to candidates."""
    with sqlite3.connect(str(db_path)) as db:
        tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "documents" not in tables:
            raise ValueError("Existing math index is not built")
        counts = dict(db.execute("SELECT tier, COUNT(*) FROM documents GROUP BY tier"))
        result = {"indexed_curated": counts.get("curated", 0),
                  "indexed_unreviewed_import": counts.get("unreviewed_import", 0)}
        if "source_registry" in tables:
            result["source_registered"] = db.execute(
                "SELECT COUNT(*) FROM source_registry").fetchone()[0]
        if "classified_knowledge" in tables:
            result["imported_assigned_level"] = db.execute(
                "SELECT COUNT(*) FROM classified_knowledge WHERE source_tier='unreviewed_import' "
                "AND difficulty_level IS NOT NULL").fetchone()[0]
        if "knowledge_review_signals" in tables:
            result["review_signals"] = db.execute(
                "SELECT COUNT(*) FROM knowledge_review_signals").fetchone()[0]
        return result
