"""Gate editorial ratings on explicit source snapshots and reviewer evidence.

Not an automated verifier. A reviewer-signed assertion remains a *reported*
human judgment; the program can test schema, source identity and audit trail,
but cannot verify whether the reviewer actually checked the mathematics.
No imported mathematical knowledge is promoted without an explicit decision.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3


ALLOWED_IMPORTANCE={"important","core","not_important","pending"}
SCHEMA="1"


def apply_review_decisions(db_path: str | Path, decisions: list[dict]) -> dict:
    """Atomically store evidence-attached reviewer decisions in separate overlay."""
    if not isinstance(decisions,list):
        raise ValueError("review decisions must be a list")
    if len({d.get("id") for d in decisions}) != len(decisions):
        raise ValueError("Duplicate review decisions")
    approved=0
    with sqlite3.connect(str(db_path)) as db:
        needed={"documents","source_registry","classified_knowledge"}
        tables={x[0] for x in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not needed <= tables:
            raise ValueError("Review requires registered, classified source database")
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS knowledge_editorial_decisions (
             id TEXT PRIMARY KEY,
             source_sha256 TEXT NOT NULL, importance TEXT NOT NULL,
             assessed_level INTEGER,
             importance_reason TEXT NOT NULL, grade_reason TEXT NOT NULL,
             reference_locator TEXT NOT NULL, reviewer TEXT NOT NULL,
             reviewed_on TEXT NOT NULL, review_digest TEXT NOT NULL
        )""")
        for d in decisions:
            cid=d.get("id")
            if not isinstance(cid,str) or not cid:
                raise ValueError("Review missing exact source concept ID")
            row=db.execute("""SELECT r.source_sha256,c.importance_status
                FROM source_registry r JOIN classified_knowledge c ON c.id=r.id
                WHERE r.id=?""",(cid,)).fetchone()
            if row is None:
                raise ValueError("Only source-registered theorem statements can be reviewed")
            sha, current=row
            # Rehash the current source body instead of trusting a stale
            # registration table alone.
            raw=db.execute("SELECT record FROM documents WHERE id=?",(cid,)).fetchone()
            record=json.loads(raw[0])
            name=record.get("en","")
            formal=record.get("formal","")
            prefix="theorem "+name
            if not formal.startswith(prefix):
                raise ValueError("Malformed source theorem after registration")
            body=formal[len(prefix):].strip()
            if hashlib.sha256(body.encode("utf-8")).hexdigest()!=sha:
                raise ValueError("Source theorem changed after registration")
            if d.get("source_sha256")!=sha:
                raise ValueError("Review has stale or missing source statement hash")
            importance=d.get("importance")
            if importance not in ALLOWED_IMPORTANCE:
                raise ValueError("Unrecognized importance label")
            grade=d.get("level")
            if grade is not None and (type(grade) is not int or not 1<=grade<=5):
                raise ValueError("Actual learning level must be 1..5 or null")
            if importance in {"important","core"} and grade is None:
                raise ValueError("Important decisions require assessed learning level")
            reviewer=d.get("reviewer","")
            reviewed=d.get("reviewed_on","")
            reference=d.get("reference_locator","")
            rationale=d.get("importance_reason","")
            grade_reason=d.get("grade_reason","")
            if any(not isinstance(v,str) or not v.strip() for v in
                   (reviewer,reviewed,reference,rationale,grade_reason)):
                raise ValueError("Review requires reviewer, date, exact citation and reasons")
            try:
                date.fromisoformat(reviewed)
            except (TypeError,ValueError):
                raise ValueError("Invalid ISO review date")
            if "http" not in reference and ":" not in reference:
                raise ValueError("Reference must identify source location, not a vague topic")
            decision={
                "id":cid,"source_sha256":sha,"importance":importance,
                "level":grade,"importance_reason":rationale.strip(),
                "grade_reason":grade_reason.strip(),
                "reference_locator":reference.strip(),"reviewer":reviewer.strip(),
                "reviewed_on":reviewed,
            }
            digest=hashlib.sha256(json.dumps(
                decision,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            db.execute("INSERT OR REPLACE INTO knowledge_editorial_decisions VALUES "
                       "(?,?,?,?,?,?,?,?,?,?)",
                       (cid,sha,importance,grade,rationale.strip(),grade_reason.strip(),
                        reference.strip(),reviewer.strip(),reviewed,digest))
            approved+=1
        db.execute("INSERT OR REPLACE INTO metadata VALUES "
                   "('editorial_review_schema',?)",(SCHEMA,))
        db.commit()
        total=db.execute("SELECT COUNT(*) FROM knowledge_editorial_decisions").fetchone()[0]
    return {"decisions_written":approved,"total_reviewed_records":total,
            "status":"reviewer_assertions_not_automated_mathematical_certification"}


def reviewer_coverage(db_path: str | Path):
    with sqlite3.connect(str(db_path)) as db:
        total=db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE "
                          "name='knowledge_editorial_decisions'").fetchone()
        rated=0
        details=[]
        if exists:
            details=[{"importance":label,"level":level,"count":count}
                     for label,level,count in db.execute(
                       "SELECT importance,assessed_level,COUNT(*) "
                       "FROM knowledge_editorial_decisions "
                       "GROUP BY importance,assessed_level")]
            rated=sum(x["count"] for x in details)
    return {"registered_theorems":total,"explicit_review_decisions":rated,
            "remaining_unreviewed":total-rated,"reviewed_breakdown":details,
            "scope":"recorded_human_assertions_with_source_snapshots"}
