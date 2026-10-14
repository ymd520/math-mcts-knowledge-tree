"""Pinned mathlib file-level author and copyright provenance for all modules.

Distinct module files are read directly from a repository at the *exact* source
commit. The author listing is from the module file header, not the individual
mathematical theorem's historical discoverer.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from .attribution import module_source_path,parse_file_header
from .source_registry import SOURCE_COMMIT


def index_module_authors(db_path: str|Path, root: str|Path) -> dict:
    root=Path(root).resolve()
    checked=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],
                           text=True,capture_output=True,check=True).stdout.strip()
    if checked!=SOURCE_COMMIT:
        raise ValueError("Refuse unpinned Mathlib file authors")
    with sqlite3.connect(str(db_path)) as db:
        rows=db.execute("SELECT DISTINCT module FROM source_registry ORDER BY module").fetchall()
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TABLE IF EXISTS mathlib_source_file_credit")
        db.execute("""CREATE TABLE mathlib_source_file_credit (
          source_module TEXT PRIMARY KEY,
          source_commit TEXT NOT NULL,
          source_file TEXT NOT NULL,
          header_authors_json TEXT NOT NULL,
          copyright_notice TEXT NOT NULL,
          file_sha256 TEXT,
          credit_status TEXT NOT NULL
        )""")
        counts=Counter()
        entries=[]
        for (module,) in rows:
            try:
                path=module_source_path(module)
                source=(root/path).resolve()
                if source.parent==root or not source.is_relative_to(root):
                    raise ValueError("Unsafe module source path")
                if not source.is_file():
                    raise FileNotFoundError(path)
                data=source.read_bytes()
                header=parse_file_header(data.decode("utf-8"))
                credit="file_header_authors_recorded" if header["module_header_authors"] else "file_header_author_not_declared"
                entries.append((module,SOURCE_COMMIT,path,
                                json.dumps(header["module_header_authors"],ensure_ascii=False),
                                header["module_header_copyright"],
                                hashlib.sha256(data).hexdigest(),credit))
            except (FileNotFoundError,UnicodeDecodeError,ValueError):
                entries.append((module,SOURCE_COMMIT,module.replace(".","/")+".lean",
                                "[]","","","source_file_missing_or_unreadable"))
                credit="source_file_missing_or_unreadable"
            counts[credit]+=1
            if len(entries)>=500:
                db.executemany("INSERT INTO mathlib_source_file_credit VALUES (?,?,?,?,?,?,?)",entries)
                entries=[]
        if entries:
            db.executemany("INSERT INTO mathlib_source_file_credit VALUES (?,?,?,?,?,?,?)",entries)
        db.execute("CREATE INDEX idx_mathlib_credit_status ON mathlib_source_file_credit(credit_status)")
        n=db.execute("SELECT COUNT(*) FROM mathlib_source_file_credit").fetchone()[0]
        if n!=len(rows):
            raise RuntimeError("Missing upstream source module credit")
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('mathlib_module_credit_commit',?)",
                   (SOURCE_COMMIT,))
        db.commit()
        sources=db.execute("""SELECT COUNT(*) FROM source_registry s
         JOIN mathlib_source_file_credit m ON m.source_module=s.module""").fetchone()[0]
        original=db.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
        if sources!=original:
            raise RuntimeError("Not all theorem source modules linked to file credits")
    return {"unique_modules":n,"linked_theorems":sources,"registered_theorems":original,
            "by_status":dict(sorted(counts.items())),
            "commit":SOURCE_COMMIT,
            "authorship_scope":"module_source_file_not_individual_math_theorem",
            "unknown_historical_theorem_authors":original}


def module_credit(db_path: str|Path,module: str) -> dict|None:
    with sqlite3.connect(str(db_path)) as db:
        row=db.execute("""SELECT source_file,header_authors_json,
          copyright_notice,file_sha256,credit_status FROM mathlib_source_file_credit
          WHERE source_module=?""",(module,)).fetchone()
    if not row:
        return None
    return {"module":module,"file":row[0],"module_header_authors":json.loads(row[1]),
            "copyright_notice":row[2],"file_sha256":row[3],"status":row[4],
            "author_scope":"file_header_only",
            "original_theorem_author":"not_individually_identified"}
