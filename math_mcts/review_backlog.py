"""Full mathematical provenance, difficulty and importance audit backlog.

A backlog is NOT an automatic mathematical review. Every upstream theorem is
exported exactly once with citation and current human-review status; title
similarity and dependency reuse NEVER silently promote importance or grades.
"""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import sqlite3
from collections import Counter
from .attribution import source_credit


def export_review_backlog(db_path: str | Path, output_path: str | Path) -> dict:
    counts=Counter()
    path=Path(output_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(str(db_path)) as db:
        tables={r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"documents","source_registry","classified_knowledge"}<=tables:
            raise ValueError("Classify registered knowledge first")
        editor="knowledge_editorial_decisions" in tables
        extracted="lean_full_declarations" in tables
        query=("SELECT r.id,d.record,c.domain_cn,r.source_sha256,"+
               ("ed.importance,ed.assessed_level,ed.reviewer,ed.reviewed_on"
                if editor else "NULL,NULL,NULL,NULL")+
               (",lf.type_sha256,lf.leading_pi_binders"
                if extracted else ",NULL,NULL")+
               " FROM source_registry r JOIN documents d ON d.id=r.id "
               "JOIN classified_knowledge c ON c.id=r.id "+
               ("LEFT JOIN knowledge_editorial_decisions ed ON ed.id=r.id " if editor else "")+
               ("LEFT JOIN lean_full_declarations lf ON lf.id=r.id " if extracted else "")+
               "ORDER BY r.id")
        with gzip.open(path,"wt",encoding="utf-8") as out:
            for cid,blob,domain,sha,importance,level,reviewer,date,type_sha,binders in db.execute(query):
                record=json.loads(blob)
                attribution=source_credit(record,tier="unreviewed_import")
                if attribution["source_module_url"] is None:
                    raise ValueError("Registered theorem missing source module locator")
                if not importance:
                    importance="unassessed"
                if importance in {"important","core"} and level is None:
                    raise ValueError("Important theorem has no assessed difficulty")
                row={
                    "source_id":cid,"theorem_name":record.get("en"),
                    "domain":domain,"source_statement_sha256":sha,
                    "source":attribution,"importance":importance,
                    "difficulty_level":level,"reviewer":reviewer,
                    "reviewed_on":date,
                    "elaborated_type_sha256":type_sha,
                    "leading_pi_binders":binders,
                    "mathematical_conditions_approved":False,
                    "original_historical_discoverer":"not_verified",
                    "credit_note":"Math-MCTS compiles/cites existing mathematics, not its original discovery",
                }
                out.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
                counts["total"]+=1
                counts["reviewed" if reviewer else "unreviewed"]+=1
                counts["type_extracted" if type_sha else "type_not_extracted"]+=1
                if importance in {"important","core"}:
                    counts["reviewed_important"]+=1
        registry=db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
        if counts["total"]!=registry:
            raise RuntimeError("Incomplete provenance and human review backlog")
    return {"source_records":counts["total"],
            "human_reviewed":counts["reviewed"],
            "not_human_reviewed":counts["unreviewed"],
            "reviewed_important":counts["reviewed_important"],
            "lean_extracted":counts["type_extracted"],
            "lean_not_extracted":counts["type_not_extracted"],
            "coverage":"all_registered_theorems",
            "claims":"no new mathematics or automatic difficulty ratings"}
