"""SQLite FTS5 index for scalable retrieval of reviewed cards + *unreviewed* corpus.

Important/level classifications are NEVER promoted from imported mathlib
declarations. Level 5 in the imported data is an explicit 'unrated' placeholder.
Candidates stay separate from formally curated 'important' knowledge.
All compressed source shards are SHA-256 verified before indexing.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import os
import re
import sqlite3

from .knowledge import IMPORTED_DIR, KnowledgeTree
from .attribution import source_credit

_WORD = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.I)


def terms_for(text: str) -> list[str]:
    """English identifier/word tokens and CJK uni/bi/trigrams for FTS5."""
    out = set()
    for m in _WORD.finditer(text.lower()):
        word = m.group()
        if not any("\u4e00" <= ch <= "\u9fff" for ch in word):
            out.add(word)
            # Common underscore-delimited Lean identifiers remain searchable.
            out.update(x for x in word.split("_") if x)
        else:
            for n in (1, 2, 3):
                out.update(word[i:i+n] for i in range(max(0, len(word)-n+1)))
    return sorted(out)


def _insert(conn, row: dict, tier: str, level: int | None):
    blob = json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    searchable = " ".join(str(row.get(k, "")) for k in
                          ("cn", "en", "definition", "formal", "module",
                           "branch_cn", "topic_cn", "assumptions", "conclusion"))
    cid = row["id"]
    conn.execute("INSERT INTO documents(id, tier, level, domain, record) VALUES(?,?,?,?,?)",
                 (cid, tier, level, row.get("domain_en", ""), blob))
    rid = conn.execute("SELECT rowid FROM documents WHERE id=?", (cid,)).fetchone()[0]
    conn.execute("INSERT INTO term_index(rowid, terms) VALUES(?,?)",
                 (rid, " ".join(terms_for(searchable))))


def build_index(db_path: str | Path, *, candidate_limit: int = 100000,
                include_curated: bool = True, include_imported: bool = True,
                imported_root: str | Path = IMPORTED_DIR) -> dict:
    """Build atomically; imported selection round-robins domains, not source order.

    Imported candidates are indexed without adding them to the trusted catalog.
    Reject malformed shards and duplicate identifiers instead of silently
    changing their meaning. This index may be rebuilt from immutable sources.
    """
    if candidate_limit < 0:
        raise ValueError("candidate_limit must be nonnegative")
    output = Path(db_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".building")
    temp.unlink(missing_ok=True)
    conn = sqlite3.connect(str(temp))
    try:
        conn.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, tier TEXT NOT NULL, "
                     "level INTEGER, domain TEXT NOT NULL, record TEXT NOT NULL)")
        conn.execute("CREATE INDEX ix_tier_level ON documents(tier, level)")
        conn.execute("CREATE VIRTUAL TABLE term_index USING fts5(terms, tokenize='unicode61')")
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        imported_count = 0
        if include_curated:
            tree = KnowledgeTree.load()
            for c in tree.concepts:
                _insert(conn, vars(c), "curated", c.level)
        curated_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if include_imported:
            root = Path(imported_root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            conn.execute("CREATE TABLE staging (id TEXT PRIMARY KEY, domain TEXT NOT NULL, "
                         "record TEXT NOT NULL)")
            seen_statements = set()
            staged_count = 0
            for item in manifest["files"]:
                shard = (root / item["shard"]).resolve()
                if shard.parent != root.resolve():
                    raise ValueError("Shard path escapes imported root")
                data = shard.read_bytes()
                if hashlib.sha256(data).hexdigest() != item["shard_sha256"]:
                    raise ValueError("Imported shard hash mismatch: " + item["shard"])
                rows = json.loads(gzip.decompress(data))["concepts"]
                if len(rows) != item["card_count"]:
                    raise ValueError("Imported shard count mismatch")
                for row in rows:
                    # The source data has placeholder level 5 and pending review.
                    # The raw original grade is retained in record for audit.
                    if not row.get("formal") and not row.get("definition"):
                        continue
                    source_hash = row.get("original_metadata", {}).get("陈述SHA256")
                    if source_hash:
                        if source_hash in seen_statements:
                            raise ValueError("Duplicate imported formal statement hash")
                        seen_statements.add(source_hash)
                    blob = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                    conn.execute("INSERT INTO staging VALUES(?,?,?)",
                                 (row["id"], row.get("domain_en", "Unknown"), blob))
                    staged_count += 1
            # Balanced *domain* admission, not invented school-grade allocation.
            query = """SELECT record FROM (
                      SELECT id, domain, record, ROW_NUMBER() OVER
                          (PARTITION BY domain ORDER BY id) AS domain_rank
                      FROM staging
                      ) ORDER BY domain_rank, domain, id LIMIT ?"""
            for (blob,) in conn.execute(query, (candidate_limit,)):
                row = json.loads(blob)
                _insert(conn, row, "unreviewed_import", None)
                imported_count += 1
            conn.execute("DROP TABLE staging")
        conn.execute("INSERT INTO metadata VALUES('schema', '1')")
        conn.execute("INSERT INTO metadata VALUES('curated_count', ?)",
                     (str(curated_count),))
        conn.execute("INSERT INTO metadata VALUES('unreviewed_candidate_count', ?)",
                     (str(imported_count),))
        conn.execute("INSERT INTO metadata VALUES('target_important_l1_l4', '100000')")
        conn.execute("PRAGMA optimize")
        conn.commit()
        conn.close()
        os.replace(temp, output)
    except Exception:
        conn.close()
        temp.unlink(missing_ok=True)
        raise
    return {"curated": curated_count, "unreviewed_candidates": imported_count,
            "total_indexed": curated_count + imported_count,
            "status": "source_candidates_not_automatically_important"}


def fast_search(db_path: str | Path, query: str, *, top_k: int = 10,
                candidate_pool: int = 400, tier: str | None = None,
                registered_only: bool = False) -> list[dict]:
    """FTS retrieval in a fixed shortlist; no all-catalog Concept allocation."""
    if top_k <= 0 or not query.strip():
        return []
    tokens = terms_for(query)
    if not tokens:
        return []
    # Build safe FTS MATCH expression without allowing raw query syntax.
    match = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
    with sqlite3.connect(str(db_path)) as conn:
        count = min(max(top_k, candidate_pool), 10000)
        where = "AND d.tier=?" if tier else ""
        if registered_only:
            # Enforce the independent provenance registry, not merely the
            # presence of a source-looking field inside the JSON payload.
            where += (" AND EXISTS (SELECT 1 FROM source_registry sr"
                      " WHERE sr.id=d.id)")
        sql = f"""SELECT d.record, d.tier, d.level, bm25(term_index) AS score
                  FROM term_index JOIN documents d ON d.rowid=term_index.rowid
                  WHERE term_index MATCH ? {where}
                  ORDER BY score ASC, d.id ASC LIMIT ?"""
        args = (match, tier, count) if tier else (match, count)
        candidates = conn.execute(sql, args).fetchall()
    # Stable rerank: exact name matching before BM25, provenance retained.
    key = query.casefold().strip()
    def ordering(item):
        row = json.loads(item[0])
        name = (row.get("cn", "") + " " + row.get("en", "")).casefold()
        exact = row.get("cn", "").casefold() == key or row.get("en", "").casefold() == key
        return (not exact, key not in name, item[3], row["id"])
    candidates.sort(key=ordering)
    return [{**json.loads(blob),
             "attribution": source_credit(json.loads(blob), tier=src),
             "index_tier": src, "indexed_level": level,
             "lexical_score": score} for blob, src, level, score in candidates[:top_k]]


def index_stats(db_path: str | Path) -> dict:
    with sqlite3.connect(str(db_path)) as conn:
        meta = dict(conn.execute("SELECT key, value FROM metadata"))
        groups = conn.execute("SELECT tier, level, COUNT(*) FROM documents "
                              "GROUP BY tier, level").fetchall()
    return {"metadata": meta,
            "counts_by_tier_level": [{"tier": a, "level": b, "count": c}
                                     for a, b, c in groups]}
