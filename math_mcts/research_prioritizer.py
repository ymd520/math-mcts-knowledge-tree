"""Focus-aware review ordering over Math-MCTS's existing source index.

This ranks *cases worth a human mathematical audit*, not real mathematical
importance. Names, modules and lexical overlap are proxy evidence only.
No candidate is promoted into the curated catalog.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from .fast_index import terms_for


def _expression(query: str) -> str:
    ts = terms_for(query)[:24]
    return " OR ".join('"' + x.replace('"', '""') + '"' for x in ts)


def prioritize(db_path: str | Path, focus: str, *, limit: int = 50,
               domain: str | None = None) -> list[dict]:
    if not focus.strip():
        raise ValueError("Nonempty research focus required")
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    q = _expression(focus)
    if not q:
        return []
    with sqlite3.connect(str(db_path)) as db:
        known = {x[0] for x in db.execute("SELECT name FROM sqlite_master")}
        required = {"documents", "term_index", "classified_knowledge", "knowledge_review_signals"}
        if not required <= known:
            raise ValueError("Build, register, classify and review existing source index first")
        # FTS controls the database scan. The priority calculation only
        # reranks a capped *retrieved candidate pool*, not all imported cards.
        sql = """SELECT d.id, d.record, c.domain_cn, c.knowledge_kind,
                        c.registration_status, c.importance_status,
                        c.difficulty_level, r.review_priority, r.anomaly_score,
                        r.reason_codes, r.same_name_count, r.same_statement_count
                 FROM term_index f JOIN documents d ON d.rowid=f.rowid
                 JOIN classified_knowledge c ON c.id=d.id
                 JOIN knowledge_review_signals r ON r.id=d.id
                 WHERE term_index MATCH ? AND d.tier='unreviewed_import'"""
        params = [q]
        if domain:
            sql += " AND c.domain_cn=?"
            params.append(domain)
        sql += " ORDER BY bm25(term_index), d.id LIMIT ?"
        params.append(min(10000, max(limit * 25, 500)))
        found = db.execute(sql, params).fetchall()
    goal_terms = set(terms_for(focus))
    ranked = []
    for (cid, raw, field, kind, source_status, importance,
         level, priority, anomaly, reasons, names, statements) in found:
        if importance != "importance_unrated" or level is not None:
            raise ValueError("Imported source incorrectly promoted: " + cid)
        row = json.loads(raw)
        title_terms = set(terms_for(str(row.get("en", "")) + " " + str(row.get("cn", ""))))
        module_terms = set(terms_for(str(row.get("module", ""))))
        name_hits = sorted(goal_terms & title_terms)
        module_hits = sorted(goal_terms & module_terms)
        # Scores only order audit workload. Negative points signal unresolved
        # validation risks, not mathematical falsehood.
        lexical = 8 * len(name_hits) + 2 * len(module_hits)
        score = lexical + int(priority) - int(anomaly)
        ranked.append({
            "id": cid, "name": row.get("en") or row.get("cn"),
            "module": row.get("module"), "domain": field, "kind": kind,
            "source_registration": source_status,
            "inspection_priority_score": score,
            "score_is_mathematical_importance": False,
            "focus_name_hits": name_hits, "focus_module_hits": module_hits,
            "existing_review_priority": int(priority),
            "existing_anomaly_score": int(anomaly),
            "same_name_count": int(names),
            "same_statement_count": int(statements),
            "review_reason_codes": json.loads(reasons),
            "source_statement_sha256": (row.get("original_metadata") or {}).get("陈述SHA256"),
            "curation_status": "unreviewed_import",
            "level": None, "mathematical_proof_verified_this_run": False,
        })
    ranked.sort(key=lambda x: (-x["inspection_priority_score"], x["id"]))
    return ranked[:limit]
