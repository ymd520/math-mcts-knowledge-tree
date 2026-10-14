"""Reproducible three-axis classification of curated and imported mathematics.

Axis A: inclusion in a mathematical statement knowledge layer.
Axis B: importance assessment (independent from mathematical level).
Axis C: learning difficulty grade (unrated is NULL, never coerced from
the source corpus's placeholder level=5).

Domain/topic categorization uses the original Mathlib module path. It is an
indexing taxonomy, NOT a scientific assertion about theorem semantics.
Existing source shards are the durable records; this SQLite table is a
rebuildable, indexed materialized view with per-record provenance.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import sqlite3

from .fast_index import terms_for
from .knowledge import _normalize_imported_domain

SCHEMA_VERSION = "1"
_IMPORT_TIER = "unreviewed_import"
_CURATED_TIER = "curated"
_STATUS_REGISTERED = "source_statement_registered"
_STATUS_STANDARD = "standard_card_source_pending"
_STATUS_CURATED = "curated_entry"
_IMPORTANCE_PENDING = "importance_unrated"


def _classify(row: dict, tier: str, registry: dict[str, str] | None) -> tuple:
    cid = row["id"]
    module = str(row.get("module") or "")
    metadata = row.get("original_metadata") or {}
    if tier == _CURATED_TIER:
        level = row.get("level")
        if type(level) is not int or not 1 <= level <= 5:
            raise ValueError(f"Invalid curated grade: {cid}")
        tags = set(row.get("tags") or [])
        importance = ("existing_core_tag" if "核心" in tags
                      else "existing_important_tag" if "重要" in tags
                      else "untagged")
        grade_status = "existing_curated_level"
        status = _STATUS_CURATED
        domain_cn = str(row.get("domain_cn") or "待分类")
        domain_en = str(row.get("domain_en") or "Unknown")
        subfield = str(row.get("branch_cn") or "未划分分支")
        topic = str(row.get("topic_cn") or "未划分主题")
        kind = str(row.get("kind") or "数学知识")
        provenance_hash = str(row.get("statement_sha256") or "")
    else:
        if tier != _IMPORT_TIER:
            raise ValueError(f"Unknown knowledge tier: {tier}")
        # The imported source's level=5 is an ungraded placeholder.
        level = None
        grade_status = "ungraded_source_placeholder"
        importance = _IMPORTANCE_PENDING
        domain_cn, domain_en = _normalize_imported_domain(row)
        if not domain_cn:
            domain_cn, domain_en = "待分类", "Unclassified"
        source_domain = str(row.get("domain_en") or "")
        segments = module.split(".")
        # Subfields/topics are *module paths*, not inferred mathematical topics.
        subfield = source_domain or (segments[1] if len(segments) > 1 else "Unknown")
        topic = ".".join(segments[2:4]) if len(segments) > 2 else "Unspecified"
        raw_type = metadata.get("类型")
        kind = "定理声明" if raw_type == "upstream_theorem" else "标准知识卡"
        if registry is None:
            if raw_type != "curated_standard_card":
                raise ValueError(f"Unverified theorem has no registry: {cid}")
            status = _STATUS_STANDARD
            provenance_hash = str(metadata.get("陈述SHA256") or "")
        else:
            if raw_type != "upstream_theorem":
                raise ValueError(f"Registry maps non-theorem: {cid}")
            status = _STATUS_REGISTERED
            provenance_hash = registry["source_sha256"]
            if registry["importance_status"] != "unreviewed_importance":
                raise ValueError(f"Unexpected imported importance tag: {cid}")
    return (cid, tier, domain_cn, domain_en, subfield, topic, kind,
            status, importance, level, grade_status, provenance_hash, module)


def classify_knowledge(db_path: str | Path) -> dict:
    """Materialize and classify all records; reject loss, grade inflation.

    Requires prior source_registry registration, which independently verified
    original statement hashes. All 100k source candidates are included:
    source-registered theorem statements and separately labeled standard
    knowledge cards. The 16 standard cards do not masquerade as theorem proofs.
    """
    with sqlite3.connect(str(db_path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='source_registry'").fetchone():
            raise ValueError("Run source registration before classifying knowledge")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                          "AND name='metadata'").fetchone():
            raise ValueError("Missing source index metadata")
        # BEGIN before DDL: a classification failure must roll back and retain
        # the previous working knowledge view rather than destroying it.
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE IF EXISTS classified_knowledge")
        db.execute("""CREATE TABLE classified_knowledge (
            id TEXT PRIMARY KEY REFERENCES documents(id),
            source_tier TEXT NOT NULL,
            domain_cn TEXT NOT NULL,
            domain_en TEXT NOT NULL,
            source_subfield TEXT NOT NULL,
            source_topic TEXT NOT NULL,
            knowledge_kind TEXT NOT NULL,
            registration_status TEXT NOT NULL,
            importance_status TEXT NOT NULL,
            difficulty_level INTEGER,
            difficulty_status TEXT NOT NULL,
            source_statement_sha256 TEXT NOT NULL,
            source_module TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX idx_knowledge_domain_kind ON "
                   "classified_knowledge(domain_cn, knowledge_kind, id)")
        db.execute("CREATE INDEX idx_knowledge_status ON "
                   "classified_knowledge(registration_status, id)")
        db.execute("CREATE INDEX idx_knowledge_importance ON "
                   "classified_knowledge(importance_status, difficulty_level, id)")
        counts = Counter()
        by_domain = Counter()
        kinds = Counter()
        subfields = Counter()
        batch = []
        reader = db.execute("""SELECT d.id, d.tier, d.record,
                                      sr.source_sha256, sr.importance_status
                               FROM documents d LEFT JOIN source_registry sr
                               ON sr.id=d.id ORDER BY d.id""")
        total = 0
        for cid, tier, raw, digest, source_importance in reader:
            entry = json.loads(raw)
            if entry.get("id") != cid:
                raise ValueError("Document ID differs from content")
            linked = ({"source_sha256": digest,
                       "importance_status": source_importance} if digest else None)
            item = _classify(entry, tier, linked)
            batch.append(item)
            counts[item[7]] += 1
            by_domain[item[2]] += 1
            kinds[item[6]] += 1
            subfields[item[4]] += 1
            total += 1
            if len(batch) >= 1000:
                db.executemany("INSERT INTO classified_knowledge VALUES("
                               "?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                batch.clear()
        if batch:
            db.executemany("INSERT INTO classified_knowledge VALUES("
                           "?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
        expected = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if total != expected:
            raise RuntimeError(f"Classification cardinality mismatch: {total}/{expected}")
        registered = db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
        if counts[_STATUS_REGISTERED] != registered:
            raise RuntimeError("Registered statement coverage mismatch")
        source_total = db.execute("SELECT COUNT(*) FROM documents WHERE tier=?",
                                  (_IMPORT_TIER,)).fetchone()[0]
        if counts[_STATUS_REGISTERED] + counts[_STATUS_STANDARD] != source_total:
            raise RuntimeError("Imported source knowledge lost in classification")
        invalid = db.execute("SELECT COUNT(*) FROM classified_knowledge "
                             "WHERE source_tier=? AND (difficulty_level IS NOT NULL "
                             "OR importance_status<>?)",
                             (_IMPORT_TIER, _IMPORTANCE_PENDING)).fetchone()[0]
        if invalid:
            raise RuntimeError("Source grade / importance was automatically promoted")
        db.execute("INSERT OR REPLACE INTO metadata VALUES"
                   "('knowledge_classification_schema', ?)", (SCHEMA_VERSION,))
        db.execute("INSERT OR REPLACE INTO metadata VALUES"
                   "('knowledge_classification_count', ?)", (str(total),))
        db.commit()
    return {
        "schema": SCHEMA_VERSION,
        "total_knowledge_records": total,
        "curated_count": counts[_STATUS_CURATED],
        "source_knowledge_imported": source_total,
        "source_registered_theorems": counts[_STATUS_REGISTERED],
        "source_standard_cards_pending": counts[_STATUS_STANDARD],
        "by_domain": dict(sorted(by_domain.items())),
        "by_kind": dict(sorted(kinds.items())),
        "source_subfield_count": len(subfields),
        "source_subfields": dict(sorted(subfields.items())),
        "importance_unrated_new_source_records": source_total,
        "difficulty_unrated_new_source_records": source_total,
        "status": "mathematical_knowledge_classified_separate_from_importance_and_difficulty",
    }


class KnowledgeBank:
    """Indexed retrieval/browsing without loading 100k Concept objects in RAM."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        with sqlite3.connect(str(self.db_path)) as db:
            ok = db.execute("SELECT 1 FROM sqlite_master WHERE name="
                            "'classified_knowledge'").fetchone()
            if not ok:
                raise ValueError("Build and classify the knowledge index first")

    def get(self, cid: str) -> dict | None:
        with sqlite3.connect(str(self.db_path)) as db:
            row = db.execute(
                "SELECT d.record, c.domain_cn, c.source_subfield, c.source_topic,"
                "c.knowledge_kind, c.registration_status, c.importance_status,"
                "c.difficulty_level FROM classified_knowledge c "
                "JOIN documents d ON d.id=c.id WHERE c.id=?", (cid,)).fetchone()
        if row is None:
            return None
        return _present(row)

    def browse(self, *, domain: str | None = None, kind: str | None = None,
               source_tier: str | None = None, after_id: str = "",
               limit: int = 100) -> list[dict]:
        if not 1 <= limit <= 500:
            raise ValueError("Browse limit must be between 1 and 500")
        filters, params = ["c.id>?"], [after_id]
        if domain:
            filters.append("c.domain_cn=?")
            params.append(domain)
        if kind:
            filters.append("c.knowledge_kind=?")
            params.append(kind)
        if source_tier:
            filters.append("c.source_tier=?")
            params.append(source_tier)
        sql = ("SELECT d.record, c.domain_cn, c.source_subfield, c.source_topic,"
               "c.knowledge_kind, c.registration_status, c.importance_status,"
               "c.difficulty_level FROM classified_knowledge c "
               "JOIN documents d ON d.id=c.id WHERE " + " AND ".join(filters) +
               " ORDER BY c.id LIMIT ?")
        with sqlite3.connect(str(self.db_path)) as db:
            rows = db.execute(sql, (*params, limit)).fetchall()
        return [_present(x) for x in rows]

    def search(self, query: str, *, domain: str | None = None,
               kind: str | None = None, source_tier: str | None = None,
               top_k: int = 10) -> list[dict]:
        if not query.strip() or top_k <= 0:
            return []
        if top_k > 500:
            raise ValueError("Search maximum top_k is 500")
        tokens = terms_for(query)
        if not tokens:
            return []
        match = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
        filters, params = ["term_index MATCH ?"], [match]
        if domain:
            filters.append("c.domain_cn=?")
            params.append(domain)
        if kind:
            filters.append("c.knowledge_kind=?")
            params.append(kind)
        if source_tier:
            filters.append("c.source_tier=?")
            params.append(source_tier)
        sql = ("SELECT d.record, c.domain_cn, c.source_subfield, c.source_topic,"
               "c.knowledge_kind, c.registration_status, c.importance_status,"
               "c.difficulty_level FROM term_index "
               "JOIN documents d ON d.rowid=term_index.rowid "
               "JOIN classified_knowledge c ON c.id=d.id WHERE " +
               " AND ".join(filters) +
               " ORDER BY bm25(term_index) ASC, d.id ASC LIMIT ?")
        with sqlite3.connect(str(self.db_path)) as db:
            rows = db.execute(sql, (*params, top_k)).fetchall()
        return [_present(x) for x in rows]


    def mcts_scope(self, query: str, *, max_concepts: int = 200,
                   domain: str | None = None):
        """Create a bounded KnowledgeTree shortlist for the existing MCTS engine.

        Grades remain unassessed for imported statements; source metadata is
        retained. This does not turn colliding names into valid mathematical
        inference. Full-catalog dependency closure is NOT claimed by the
        reduced shortlist.
        """
        from .knowledge import Concept, KnowledgeTree
        if not 2 <= max_concepts <= 500:
            raise ValueError("MCTS shortlist must contain 2..500 concepts")
        hits = self.search(query, domain=domain, top_k=max_concepts)
        ids = [hit["id"] for hit in hits]
        if not ids:
            return KnowledgeTree([], meta={"source": "indexed_shortlist",
                                            "query": query})
        with sqlite3.connect(str(self.db_path)) as db:
            raw = {}
            for cid in ids:
                item = db.execute("SELECT tier, record FROM documents WHERE id=?",
                                  (cid,)).fetchone()
                if item is None:
                    raise ValueError("Indexed document missing: " + cid)
                raw[cid] = item
        concepts = []
        for cid in ids:
            tier, blob = raw[cid]
            row = json.loads(blob)
            if tier == _IMPORT_TIER:
                domain_cn, domain_en = _normalize_imported_domain(row)
                row["domain_cn"], row["domain_en"] = domain_cn, domain_en
                row["level_status"] = "ungraded_source_placeholder"
                row["tags"] = [t for t in row.get("tags", [])
                               if t not in {"核心", "重要"}]
            concepts.append(Concept(**row))
        return KnowledgeTree(concepts, meta={
            "source": "indexed_shortlist",
            "query": query,
            "grade_warning": "imported level 5 is an ungraded placeholder",
            "search_view": True,
        })


def _present(row) -> dict:
    raw, domain, subfield, topic, kind, status, importance, level = row
    record = json.loads(raw)
    return {
        "id": record["id"],
        "name": record.get("cn") or record.get("en"),
        "english_name": record.get("en"),
        "statement": record.get("formal") or record.get("definition"),
        "source_module": record.get("module", ""),
        "domain": domain,
        "source_subfield": subfield,
        "source_topic": topic,
        "kind": kind,
        "registration_status": status,
        "importance_status": importance,
        "difficulty_level": level,
    }
