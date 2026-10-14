"""Evidence-conserving prioritization for the 100k mathematics review queue.

A source theorem may be a valid record without being important. This module
produces observable review signals and possible duplicate families; it does
NOT assign difficulty, importance, proof status or semantic equivalence.

Input: validated source registry + classified knowledge view.
Output: reproducible SQLite signals and a bounded, inspectable review queue.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

SCHEMA = "1"
_WS = re.compile(r"\s+")
_PLACEHOLDER = re.compile(r"\b(?:sorry|admit)\b")
_NAME = re.compile(r"[^a-z0-9]+")
_ADVANCED_MODULES = frozenset({
    "CategoryTheory", "AlgebraicGeometry", "AlgebraicTopology",
    "RepresentationTheory", "ModelTheory", "MeasureTheory",
})


def normalized_name(name: str) -> str:
    """Exact lexical anchor only; not a mathematical equivalence judgment."""
    return _NAME.sub("", unicodedata.normalize("NFKC", name).casefold())


def statement_body(formal: str, theorem_name: str) -> str:
    prefix = "theorem " + theorem_name
    return formal[len(prefix):].strip() if formal.startswith(prefix) else ""


def review_signals(db_path: str | Path) -> dict:
    """Stream all imported records; compute source-grounded audit diagnostics.

    Uses SQL joins and indexed group statistics so full-corpus processing is
    linear except for grouping/sorting. Data is only committed after all
    registry and cardinality invariants have been checked.
    """
    counts = Counter()
    risks = Counter()
    with sqlite3.connect(str(db_path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='classified_knowledge'").fetchone():
            raise ValueError("Classify source knowledge before review signals")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='source_registry'").fetchone():
            raise ValueError("Register source statements before review signals")
        curated_names = set()
        for (raw,) in db.execute("SELECT record FROM documents WHERE tier='curated'"):
            row = json.loads(raw)
            for name in [row.get("en", ""), row.get("cn", ""), *(row.get("aliases") or [])]:
                normalized = normalized_name(str(name))
                if len(normalized) >= 8:
                    curated_names.add(normalized)
        # A transaction covers schema updates and all rows. Previous valid
        # materialization survives any validation/SQL failure.
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE IF EXISTS knowledge_review_signals")
        db.execute("""CREATE TABLE knowledge_review_signals (
            id TEXT PRIMARY KEY,
            source_statement_sha256 TEXT NOT NULL,
            source_module TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            review_priority INTEGER NOT NULL,
            anomaly_score INTEGER NOT NULL,
            review_bucket TEXT NOT NULL,
            name_family_key TEXT NOT NULL,
            normalized_statement_hash TEXT NOT NULL,
            same_name_count INTEGER NOT NULL DEFAULT 1,
            same_statement_count INTEGER NOT NULL DEFAULT 1,
            reason_codes TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX idx_review_priority ON knowledge_review_signals(review_priority DESC, id)")
        db.execute("CREATE INDEX idx_review_anomaly ON knowledge_review_signals(anomaly_score DESC, id)")
        db.execute("CREATE INDEX idx_review_name ON knowledge_review_signals(name_family_key)")
        db.execute("CREATE INDEX idx_review_statement ON knowledge_review_signals(normalized_statement_hash)")
        raw_cursor = db.execute("""SELECT d.id, d.record, c.registration_status,
                                  c.source_statement_sha256, c.source_module,
                                  c.source_subfield
            FROM documents d JOIN classified_knowledge c ON c.id=d.id
            WHERE d.tier='unreviewed_import' ORDER BY d.id""")
        batch = []
        for cid, source_blob, registration, fingerprint, module, subfield in raw_cursor:
            row = json.loads(source_blob)
            if cid != row.get("id"):
                raise ValueError("Content ID mismatch")
            formal = str(row.get("formal") or "")
            name = str(row.get("en") or "")
            body = statement_body(formal, name)
            status = str(registration)
            raw_kind = str((row.get("original_metadata") or {}).get("类型") or "")
            if status == "source_statement_registered":
                if raw_kind != "upstream_theorem":
                    raise ValueError("Source registry type mismatch")
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                original = str((row.get("original_metadata") or {}).get("陈述SHA256") or "")
                if digest != fingerprint or original != fingerprint or not body:
                    raise ValueError("Stale or tampered registered source statement: " + cid)
            if status == "standard_card_source_pending" and raw_kind != "curated_standard_card":
                raise ValueError("Standard card type mismatch")
            if status not in {"source_statement_registered", "standard_card_source_pending"}:
                raise ValueError("Unrecognized source review status")
            norm = _WS.sub(" ", unicodedata.normalize("NFKC", body)).strip()
            body_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest() if norm else ""
            name_key = normalized_name(name)
            reasons = []
            priority, anomaly = 0, 0
            anchored = name_key in curated_names
            specialized = subfield in _ADVANCED_MODULES
            if anchored:
                # Exact *name* overlap is a review lead, not a proof that
                # these declarations share assumptions/conclusions.
                reasons.append("lexical_name_matches_curated")
                priority += 45
            if specialized:
                reasons.append("specialized_module_topic")
            # Buckets are workflow routing hints, NEVER numeric difficulty.
            bucket = ("curated_title_review" if anchored
                      else "specialized_subject_review" if specialized
                      else "general_source_review")
            if status == "standard_card_source_pending":
                reasons.append("source_standard_card_not_registered_theorem")
                anomaly += 15
            elif not norm or len(norm) < 18:
                reasons.append("very_short_formal_statement")
                anomaly += 20
            if _PLACEHOLDER.search(formal):
                # Pure text scan, NOT a parser or proof checker.
                reasons.append("placeholder_keyword_in_source_text")
                anomaly += 80
            if not module.startswith("Mathlib."):
                reasons.append("module_locator_needs_review")
                anomaly += 30
            batch.append((cid, fingerprint, module, raw_kind, priority,
                          anomaly, bucket, name_key, body_hash, 1, 1,
                          json.dumps(reasons, ensure_ascii=False)))
            counts[status] += 1
            for reason in reasons:
                risks[reason] += 1
            if len(batch) == 1000:
                db.executemany("INSERT INTO knowledge_review_signals VALUES("
                               "?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                batch.clear()
        if batch:
            db.executemany("INSERT INTO knowledge_review_signals VALUES("
                           "?,?,?,?,?,?,?,?,?,?,?,?)", batch)
        count = sum(counts.values())
        expected = db.execute("SELECT COUNT(*) FROM documents WHERE tier='unreviewed_import'").fetchone()[0]
        if count != expected:
            raise RuntimeError("Review signal coverage mismatch")
        # SQL exact lexical-group frequencies are non-authoritative candidates
        # for duplicate investigation; they are never auto-merged.
        db.execute("""UPDATE knowledge_review_signals SET same_name_count=(
            SELECT COUNT(*) FROM knowledge_review_signals x
            WHERE x.name_family_key=knowledge_review_signals.name_family_key)
            WHERE name_family_key<>''""")
        db.execute("""UPDATE knowledge_review_signals SET same_statement_count=(
            SELECT COUNT(*) FROM knowledge_review_signals x
            WHERE x.normalized_statement_hash=knowledge_review_signals.normalized_statement_hash)
            WHERE normalized_statement_hash<>''""")
        # Only primary detection signals affect scores. Duplicate-family sizes
        # are added here, after the group statistics are materialized.
        db.execute("""UPDATE knowledge_review_signals SET
           anomaly_score=anomaly_score+
               CASE WHEN same_statement_count>1 THEN 35 ELSE 0 END,
           review_priority=review_priority+
               CASE WHEN same_name_count>1 THEN 12 ELSE 0 END +
               CASE WHEN same_statement_count>1 THEN 10 ELSE 0 END""")
        # Leave both axes of mathematical importance/difficulty entirely unchanged.
        check = db.execute("""SELECT COUNT(*) FROM classified_knowledge c
           JOIN knowledge_review_signals r ON c.id=r.id
           WHERE c.difficulty_level IS NOT NULL OR c.importance_status!='importance_unrated'""").fetchone()[0]
        if check:
            raise RuntimeError("Review process unexpectedly promoted source grades")
        count2 = db.execute("SELECT COUNT(*) FROM knowledge_review_signals").fetchone()[0]
        if count2 != expected:
            raise RuntimeError("Review signal loss")
        db.execute("INSERT OR REPLACE INTO metadata VALUES('knowledge_review_schema', ?)", (SCHEMA,))
        db.execute("INSERT OR REPLACE INTO metadata VALUES('knowledge_review_count', ?)", (str(count2),))
        summary = db.execute("""SELECT
            SUM(same_name_count>1), SUM(same_statement_count>1),
            SUM(review_priority>0), SUM(anomaly_score>0),
            MAX(review_priority), MAX(anomaly_score)
            FROM knowledge_review_signals""").fetchone()
        db.commit()
    return {
        "schema": SCHEMA,
        "source_knowledge_scanned": count,
        "registration_status_counts": dict(counts),
        "reason_counts": dict(sorted(risks.items())),
        "same_name_group_members": summary[0],
        "same_statement_group_members": summary[1],
        "review_priority_positive": summary[2],
        "anomaly_positive": summary[3],
        "max_review_priority": summary[4],
        "max_anomaly_score": summary[5],
        "importance_or_level_promoted": 0,
        "scope": "lexical_and_provenance_diagnostics_not_semantic_proof_or_grade",
    }


def review_queue(db_path: str | Path, *, limit: int = 100,
                 offset: int = 0, mode: str = "priority") -> list[dict]:
    """Retrieve deterministic, evidence-anchored review leads for inspection."""
    if mode not in {"priority", "anomaly", "duplicate"}:
        raise ValueError("Review queue mode must be priority, anomaly or duplicate")
    if not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("Invalid review paging parameters")
    order = {
        "priority": "r.review_priority DESC, r.anomaly_score DESC, r.id",
        "anomaly": "r.anomaly_score DESC, r.review_priority DESC, r.id",
        "duplicate": "(r.same_name_count+r.same_statement_count) DESC, r.id",
    }[mode]
    with sqlite3.connect(str(db_path)) as db:
        rows = db.execute("""SELECT r.id, r.source_module,
            r.source_statement_sha256, r.review_priority, r.anomaly_score,
            r.review_bucket, r.same_name_count, r.same_statement_count, r.reason_codes,
            d.record
            FROM knowledge_review_signals r JOIN documents d ON d.id=r.id
            ORDER BY """ + order + " LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    results = []
    for cid, module, digest, priority, anomaly, bucket, names, statements, reasons, raw in rows:
        record = json.loads(raw)
        results.append({
            "id": cid, "name": record.get("en"),
            "module": module, "source_statement_sha256": digest,
            "review_priority": priority, "anomaly_score": anomaly,
            "review_bucket": bucket,
            "same_name_family_size": names,
            "same_normalized_statement_family_size": statements,
            "reason_codes": json.loads(reasons),
            "formal_statement": record.get("formal") or record.get("definition"),
            "importance_status": "unassessed",
            "difficulty_status": "unassessed",
        })
    return results
