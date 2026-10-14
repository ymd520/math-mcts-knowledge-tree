"""Leakage-aware reproducible holdout splits grouped by source module.

A train/test split of individual theorem *names* leaks nearby lemmas.
Grouping full Mathlib modules is a stricter, reproducible partial defense,
not a guarantee against cross-module mathematical theorem leakage.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import sqlite3
from pathlib import Path

SPLITS=("train","validation","test")


def group_split(module: str, *, salt="math-mcts-lean-holdout-v1") -> str:
    if not isinstance(module,str) or not module.startswith("Mathlib."):
        raise ValueError("Missing source module")
    digest=hashlib.sha256((salt+"\0"+module).encode()).digest()
    bucket=int.from_bytes(digest[:8],"big")%100
    return "train" if bucket<80 else "validation" if bucket<90 else "test"


def create_module_splits(db_path: str | Path, manifest_path: str | Path,
                         *, salt="math-mcts-lean-holdout-v1") -> dict:
    counts=Counter()
    modules=Counter()
    manifest_path=Path(manifest_path)
    with sqlite3.connect(str(db_path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='source_registry'").fetchone():
            raise ValueError("Build source registry before preparing splits")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE IF EXISTS mathlib_holdout")
        db.execute("CREATE TABLE mathlib_holdout (id TEXT PRIMARY KEY, "
                   "source_module TEXT NOT NULL, split TEXT NOT NULL)")
        batch=[]
        for cid,module in db.execute("SELECT id,module FROM source_registry ORDER BY id"):
            split=group_split(module,salt=salt)
            batch.append((cid,module,split))
            counts[split]+=1
            modules[(module,split)]+=1
            if len(batch)==1000:
                db.executemany("INSERT INTO mathlib_holdout VALUES(?,?,?)",batch)
                batch=[]
        if batch:
            db.executemany("INSERT INTO mathlib_holdout VALUES(?,?,?)",batch)
        db.execute("CREATE INDEX idx_mathlib_holdout_split ON "
                   "mathlib_holdout(split,source_module,id)")
        leaks=db.execute("""SELECT COUNT(*) FROM (
          SELECT source_module FROM mathlib_holdout
          GROUP BY source_module HAVING COUNT(DISTINCT split)>1)""").fetchone()[0]
        if leaks:
            raise RuntimeError("A source module appears in multiple splits")
        expected=db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
        if sum(counts.values())!=expected:
            raise RuntimeError("Holdout lost source entries")
        db.commit()
    report={
        "schema":"1","source_theorems":sum(counts.values()),
        "split_counts":{s:counts[s] for s in SPLITS},
        "unique_source_modules":len(modules),
        "source_modules_spanning_multiple_splits":leaks,
        "module_assignment_hash":hashlib.sha256(json.dumps(
            sorted(((m,s) for m,s in modules)),separators=(",",":")).encode()).hexdigest(),
        "warning":"Module-level split does not rule out cross-module proof leakage"}
    manifest_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return report
