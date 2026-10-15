"""Quarantined AI-authored math knowledge exchange for a generic Math-MCTS.

This stores *statements proposed by an AI assistant*, not independently
validated theorems. Source references are unverified citations supplied by
the generating client. Search and MCTS may suggest combinations, but neither
changes proof/curation status. No database write touches the curated manifest.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import unicodedata

from .fast_index import terms_for
from .knowledge import Concept, KnowledgeTree
from .search import collide_concepts, search_concepts

SCHEMA = "math-mcts-ai-knowledge-v1"
CANDIDATE_STATUS = "unreviewed_ai_generated"
KINDS = frozenset({"definition", "theorem", "lemma", "method", "conjecture",
                   "counterexample", "heuristic", "reduction", "proof_idea"})
REQUIRED = frozenset({"local_id", "kind", "domain", "branch", "topic",
                      "title", "statement", "assumptions", "conclusion"})
OPTIONAL = frozenset({"english_title", "explanation", "proof_idea",
                      "counterexample_hint", "falsification_plan",
                      "keywords", "references"})
GENERATOR = frozenset({"system", "model", "run_id", "generated_at"})
MAX_BYTES = 8_000_000
MAX_STATEMENT = 12_000
MAX_ITEMS = 4000
SPACE = re.compile(r"\s+")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: str) -> str:
    # Lexical, NOT algebraic/theorem equivalence.
    return SPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _string(obj: dict, key: str, *, required=True, limit=2000) -> str:
    value = obj.get(key, "")
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError("invalid or missing nonempty text field " + key)
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise ValueError("invalid control character in " + key)
    return value.strip()


def _validate_reference(item: object) -> dict:
    if not isinstance(item, dict) or not {"title", "locator"} <= set(item):
        raise ValueError("reference must include title and locator")
    if set(item) - {"title", "locator", "url"}:
        raise ValueError("reference has unknown fields")
    result = {"title": _string(item, "title", limit=500),
              "locator": _string(item, "locator", limit=1000)}
    url = _string(item, "url", required=False, limit=1500)
    if url and (not url.startswith("https://") or any(ch.isspace() for ch in url)):
        raise ValueError("reference URL must be HTTPS if supplied")
    result["url"] = url
    result["source_verification"] = "not_verified_by_importer"
    return result


def _validate_item(row: object) -> dict:
    if not isinstance(row, dict):
        raise ValueError("knowledge item must be a JSON object")
    if set(row) - REQUIRED - OPTIONAL:
        raise ValueError("unknown knowledge item fields (no status/grade injection)")
    missing = REQUIRED - set(row)
    if missing:
        raise ValueError("missing required knowledge fields: " + ", ".join(sorted(missing)))
    data = {k: _string(row, k, limit=MAX_STATEMENT if k == "statement"
                      else 4000 if k in {"assumptions", "conclusion"} else 1000)
            for k in REQUIRED}
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", data["local_id"]):
        raise ValueError("local_id must be a stable short identifier")
    if data["kind"] not in KINDS:
        raise ValueError("unsupported knowledge kind")
    for key in ("english_title", "explanation", "proof_idea", "counterexample_hint",
                "falsification_plan"):
        data[key] = _string(row, key, required=False, limit=MAX_STATEMENT)
    keys = row.get("keywords", [])
    if not isinstance(keys, list) or len(keys) > 40 or any(
            not isinstance(k, str) or not k.strip() or len(k) > 120 for k in keys):
        raise ValueError("keywords must be short nonempty strings")
    data["keywords"] = list(dict.fromkeys(_canonical(k) for k in keys))
    refs = row.get("references", [])
    if not isinstance(refs, list) or len(refs) > 30:
        raise ValueError("references must be a bounded list")
    data["references"] = [_validate_reference(x) for x in refs]
    identity = json.dumps([
        _canonical(data[k]).casefold() if k in {"kind", "domain"} else _canonical(data[k])
        for k in ("kind", "domain", "statement", "assumptions", "conclusion")
    ], ensure_ascii=False, separators=(",", ":"))
    data["id"] = "AI_" + _digest(identity)[:32]
    data["identity_sha256"] = _digest(identity)
    data["statement_sha256"] = _digest(data["statement"])
    data["curation_status"] = CANDIDATE_STATUS
    data["verification_status"] = "not_independently_verified"
    data["importance_status"] = "unrated"
    data["difficulty_level"] = None
    data["proof_verified"] = False
    data["references_verified"] = False
    data["author_credit"] = "AI-authored mathematical summary/proposal; original historical credit unverified"
    return data


def validate_pack(pack: object) -> dict:
    """Fail closed; accepts assistant-proposed math, never its claims of proof."""
    if not isinstance(pack, dict) or set(pack) != {"schema", "generator", "items"}:
        raise ValueError("pack requires exactly schema, generator and items")
    if pack["schema"] != SCHEMA:
        raise ValueError("unsupported AI knowledge pack schema")
    meta = pack["generator"]
    if not isinstance(meta, dict) or set(meta) != GENERATOR:
        raise ValueError("generator requires system, model, run_id, generated_at")
    generator = {k: _string(meta, k, limit=200) for k in GENERATOR}
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", generator["run_id"]):
        raise ValueError("run_id must be a stable nonempty identifier")
    items = pack["items"]
    if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
        raise ValueError("knowledge pack must contain 1..4000 records")
    records = [_validate_item(x) for x in items]
    ids = [x["local_id"] for x in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate local_id in a generator run")
    # Provider/model/run_id are caller assertions, not authenticated metadata.
    return {"schema": SCHEMA, "generator": generator, "items": records}


def _connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_candidates(
        id TEXT PRIMARY KEY, identity_sha256 TEXT NOT NULL UNIQUE,
        domain TEXT NOT NULL, kind TEXT NOT NULL,
        record TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS ai_observations(
        run_id TEXT NOT NULL, local_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL, provenance TEXT NOT NULL,
        PRIMARY KEY(run_id, local_id))""")
    db.execute("CREATE INDEX IF NOT EXISTS ai_observation_by_candidate ON ai_observations(candidate_id)")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ai_terms USING fts5(terms, tokenize='unicode61')")
    db.execute("CREATE TABLE IF NOT EXISTS ai_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("INSERT OR IGNORE INTO ai_metadata VALUES('schema',?)", (SCHEMA,))
    if db.execute("SELECT value FROM ai_metadata WHERE key='schema'").fetchone()[0] != SCHEMA:
        db.close()
        raise ValueError("unsupported AI knowledge database schema")
    db.commit()
    return db


def ingest_pack(db_path: str | Path, pack: dict) -> dict:
    """Atomic idempotent ingest, with immutable per-run origin observations.

    Repeated identical records are linked, never upgraded. Same run/local ID
    with revised text or provenance rejects the ENTIRE batch.
    """
    normalized = validate_pack(pack)
    gen = normalized["generator"]
    with closing(_connect(db_path)) as db:
        inserted, same, linked = 0, 0, 0
        try:
            db.execute("BEGIN IMMEDIATE")
            for row in normalized["items"]:
                candidate_id = row["id"]
                existing = db.execute(
                    "SELECT record FROM ai_candidates WHERE id=?", (candidate_id,)
                ).fetchone()
                # Same identity with differing annotations preserves the first
                # version of the candidate, the new annotation in observations.
                if existing is None:
                    searchable = " ".join(str(row.get(k, "")) for k in
                        ("title","english_title","statement","assumptions",
                         "conclusion","domain","branch","topic","explanation",
                         "proof_idea","counterexample_hint","falsification_plan"))
                    searchable += " " + " ".join(row["keywords"])
                    record = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    db.execute("INSERT INTO ai_candidates VALUES(?,?,?,?,?)",
                               (candidate_id, row["identity_sha256"],
                                row["domain"], row["kind"], record))
                    rid = db.execute(
                        "SELECT rowid FROM ai_candidates WHERE id=?",
                        (candidate_id,)).fetchone()[0]
                    db.execute("INSERT INTO ai_terms(rowid,terms) VALUES(?,?)",
                               (rid, " ".join(terms_for(searchable))))
                    inserted += 1
                else:
                    same += 1
                provenance = json.dumps({
                    "generator_claim": gen, "item": row,
                    "source_authentication": "not_authenticated_by_importer",
                    "references_checked": False,
                }, sort_keys=True, ensure_ascii=False)
                old = db.execute(
                    "SELECT candidate_id,provenance FROM ai_observations "
                    "WHERE run_id=? AND local_id=?",
                    (gen["run_id"], row["local_id"])).fetchone()
                if old is not None:
                    if old != (candidate_id, provenance):
                        raise ValueError("same generator run_id/local_id has changed: "
                                         + row["local_id"])
                else:
                    db.execute(
                        "INSERT INTO ai_observations VALUES(?,?,?,?)",
                        (gen["run_id"], row["local_id"], candidate_id, provenance))
                    linked += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"items_in_pack": len(normalized["items"]), "new_candidates": inserted,
            "previously_seen_content": same, "new_observations": linked,
            "new_curated": 0, "verified_proofs": 0,
            "status": CANDIDATE_STATUS}


def ingest_file(db_path: str | Path, input_path: str | Path) -> dict:
    path = Path(input_path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("AI pack exceeds maximum byte budget")
    pack = json.loads(path.read_text(encoding="utf-8"))
    return ingest_pack(db_path, pack)


def _query(query: str) -> str:
    return " OR ".join('"' + t.replace('"', '""') + '"'
                    for t in terms_for(query)[:40])


def lookup(db_path: str | Path, query: str, *, limit=40) -> list[dict]:
    """Indexed candidate retrieval. Similarity is not proof or review."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    expr = _query(query)
    if not expr:
        return []
    with closing(_connect(db_path)) as db:
        rows = db.execute(
            "SELECT c.record, (SELECT COUNT(*) FROM ai_observations o "
            "WHERE o.candidate_id=c.id) FROM ai_terms f "
            "JOIN ai_candidates c ON c.rowid=f.rowid "
            "WHERE ai_terms MATCH ? ORDER BY bm25(ai_terms),c.id LIMIT ?",
            (expr,limit)).fetchall()
    return [{**json.loads(blob), "observation_count": count} for blob,count in rows]


def all_candidates(db_path: str | Path, *, limit=100, offset=0) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
        raise ValueError("invalid pagination")
    with closing(_connect(db_path)) as db:
        rows = db.execute(
            "SELECT record FROM ai_candidates ORDER BY id LIMIT ? OFFSET ?",
            (limit,offset)).fetchall()
    return [json.loads(row[0]) for row in rows]


def inventory(db_path: str | Path) -> dict:
    with closing(_connect(db_path)) as db:
        count = db.execute("SELECT COUNT(*) FROM ai_candidates").fetchone()[0]
        obs = db.execute("SELECT COUNT(*) FROM ai_observations").fetchone()[0]
        kinds = dict(db.execute(
            "SELECT kind,COUNT(*) FROM ai_candidates GROUP BY kind ORDER BY kind"))
    return {"unreviewed_ai_candidates":count,"generator_observations":obs,
            "by_kind":kinds,"curated_promotions":0,"independent_proofs_verified":0}


def to_candidate_concept(row: dict) -> Concept:
    """MCTS-compatible read-only overlay, explicitly NEVER a reviewed rule."""
    if row.get("curation_status") != CANDIDATE_STATUS or not row["id"].startswith("AI_"):
        raise ValueError("only quarantined AI candidate rows allowed")
    # Concept.level is an integer in the legacy search representation.
    # The level=5 placeholder is explicitly marked as UNGRADED; do not
    # treat it as a difficulty assessment, especially when ranking pairs.
    return Concept(
        id=row["id"], domain_cn=row["domain"], domain_en=row["domain"],
        branch_cn=row["branch"], topic_cn=row["topic"],
        cn=row["title"], en=row["english_title"] or row["title"],
        definition=row["statement"], formulas=[],
        level=5, level_status="ungraded_ai_candidate",
        kind=row["kind"], prereq=[], tags=["AI候选", "未核验"],
        example=row["explanation"], assumptions=row["assumptions"],
        conclusion=row["conclusion"], proof_idea=row["proof_idea"],
        misuse_counterexample=row["counterexample_hint"],
        verification_status="not_independently_verified",
        curation_status=CANDIDATE_STATUS,
        statement_sha256=row["statement_sha256"],
        knowledge_origin="AI-authored candidate; not original historical discovery",
        original_metadata={
            "identity_sha256": row["identity_sha256"],
            "claimed_references": row["references"],
            "references_verified": False,
            "importance_status": "unrated",
            "generator_observation_count": row.get("observation_count", 0),
        },
    )


def candidate_tree(db_path: str | Path, *, query: str | None = None,
                   limit=100, base_tree: KnowledgeTree | None = None) -> KnowledgeTree:
    """In-memory search overlay; does NOT mutate curated catalog or RuleBook."""
    rows = lookup(db_path, query, limit=limit) if query else all_candidates(db_path, limit=limit)
    concepts = list(base_tree.concepts) if base_tree is not None else []
    existing = {c.id for c in concepts}
    for row in rows:
        candidate = to_candidate_concept(row)
        if candidate.id in existing:
            raise ValueError("AI candidate ID collides with existing knowledge ID")
        existing.add(candidate.id)
        concepts.append(candidate)
    return KnowledgeTree(concepts, meta={
        "ai_candidate_overlay":True,
        "unreviewed_ai_candidates_in_view": len(rows),
        "catalog_unchanged":True,
    })


def query_for_research(db_path: str | Path, query: str, *,
                       limit=100, top_k=10, iterations=200) -> list[dict]:
    """Return candidate evidence for ChatGPT; existing retrieval is deterministic.

    This is NOT MCTS: search_concepts is exact-ranking, as its current
    implementation states. MCTS is used in collide_for_research below.
    """
    tree = candidate_tree(db_path, query=query, limit=limit)
    return [{**asdict(c), "retrieval_score":score, "verified":False}
            for c,_,score in search_concepts(tree,query,top_k=top_k,iterations=iterations)]


def collide_for_research(db_path: str | Path, *, seed: str | None = None,
                         limit=100, top_k=5, iterations=300,
                         base_tree: KnowledgeTree | None = None) -> list[dict]:
    """Run actual two-step existing MCTS collision search on quarantined candidates."""
    tree = candidate_tree(db_path,limit=limit,base_tree=base_tree)
    pairs = collide_concepts(tree,seed=seed,top_k=top_k,iterations=iterations)
    return [{
        "a":a.id, "b":b.id, "a_title":a.cn, "b_title":b.cn,
        "heuristic_collision_score":score,
        "conjecture_only":True, "proof_verified":False,
        "reviewed_rule_created":False,
    } for a,b,score,_ in pairs]
