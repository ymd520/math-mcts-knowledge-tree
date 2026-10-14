"""Index elaborated Lean forall-binder domains and residual conclusion AST.

Candidate equalities below are deliberately NOT proof edges. A binder domain
can contain de Bruijn variables; even exact repr equality does not guarantee
the necessary assumptions, universe constraints, or metavariable assignment.
Only a separate Lean environment type checker may certify each application.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
from .lean_reference_index import _match_source


def _fingerprint(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def index_elaborated_type_structure(db_path: str|Path,
                                    exports: str|Path) -> dict:
    lines=Path(exports).read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("No actual elaborated type exports provided")
    rows=[]
    for line in lines:
        obj=json.loads(line)
        required=("source_id","source_statement_sha256","type_binders",
                  "conclusion_ast","type_structure_source")
        if any(name not in obj for name in required):
            raise ValueError("Missing elaborated binder/conclusion structural field")
        if obj["type_structure_source"]!="actual_elaborated_lean_expr":
            raise ValueError("Type structure must come from actual Lean expression")
        binders=obj["type_binders"]
        if not isinstance(binders,list) or len(binders)>1000 or not isinstance(obj["conclusion_ast"],str):
            raise ValueError("Malformed Lean Expr telescope")
        if len(obj["conclusion_ast"])>300000 or not obj["conclusion_ast"]:
            raise ValueError("Invalid conclusion AST")
        for i,b in enumerate(binders):
            if not isinstance(b,dict) or any(not isinstance(b.get(k),str)
                                             for k in ("name","domain_ast","binder_info")):
                raise ValueError("Malformed quantified variable domain")
            if not isinstance(b.get("domain_constants"),list):
                raise ValueError("Invalid domain constant references")
            if len(b["domain_constants"])>20000:
                raise ValueError("Oversized binder references")
        rows.append(obj)
    ids=[x["source_id"] for x in rows]
    if len(ids)!=len(set(ids)):
        raise ValueError("Duplicate type structure source ID")
    with sqlite3.connect(str(db_path)) as db:
        db.execute("BEGIN IMMEDIATE")
        for x in rows:
            _match_source(db,x)
        db.execute("DROP TABLE IF EXISTS lean_type_binders")
        db.execute("DROP TABLE IF EXISTS lean_type_structure")
        db.execute("""CREATE TABLE lean_type_structure(
          source_id TEXT PRIMARY KEY,
          source_sha256 TEXT NOT NULL,
          conclusion_ast TEXT NOT NULL,
          conclusion_sha256 TEXT NOT NULL,
          binder_count INTEGER NOT NULL,
          semantic_certainty TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE lean_type_binders(
          source_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          variable_name TEXT NOT NULL,
          domain_ast TEXT NOT NULL,
          domain_sha256 TEXT NOT NULL,
          binder_info TEXT NOT NULL,
          constant_refs_json TEXT NOT NULL,
          semantic_certainty TEXT NOT NULL,
          PRIMARY KEY(source_id,ordinal)
        )""")
        db.execute("CREATE INDEX idx_type_binder_domain ON lean_type_binders(domain_sha256)")
        db.execute("CREATE INDEX idx_type_structure_conclusion ON lean_type_structure(conclusion_sha256)")
        count=0
        for obj in rows:
            cid=obj["source_id"]
            conclusion=obj["conclusion_ast"]
            db.execute("INSERT INTO lean_type_structure VALUES (?,?,?,?,?,?)",
                       (cid,obj["source_statement_sha256"],conclusion,
                        _fingerprint(conclusion),len(obj["type_binders"]),
                        "elaborated_expr_shape_not_proof"))
            for idx,b in enumerate(obj["type_binders"]):
                db.execute("INSERT INTO lean_type_binders VALUES (?,?,?,?,?,?,?,?)",
                           (cid,idx,b["name"],b["domain_ast"],
                            _fingerprint(b["domain_ast"]),b["binder_info"],
                            json.dumps(b["domain_constants"],sort_keys=True),
                            "type_domain_uninterpreted"))
                count+=1
        db.commit()
    return {"source_declarations_with_type_structure":len(rows),
            "quantified_binders":count,
            "certified_applications":0,
            "semantic_status":"actual_Lean_expression_shape_only",
            "needs":"definitional equality, substitution, assumptions and Lean proof validation"}


def candidate_type_connections(db_path: str|Path, *,
                               limit: int=100) -> list[dict]:
    """Find only exact AST-shape matches, with explicit *candidate* status."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    with sqlite3.connect(str(db_path)) as db:
        entries=db.execute("""SELECT s.source_id,b.source_id,b.ordinal,b.binder_info
          FROM lean_type_structure s JOIN lean_type_binders b
          ON s.conclusion_sha256=b.domain_sha256
          AND s.conclusion_ast=b.domain_ast
          WHERE s.source_id!=b.source_id
          ORDER BY s.source_id,b.source_id,b.ordinal LIMIT ?""",(limit,)).fetchall()
    return [{"producer":p,"consumer":c,"consumer_binder_index":i,
             "binder_info":bi,
             "relation":"exact_elaborated_expr_ast_candidate",
             "proof_status":"no_proof_not_typechecked_as_application"}
            for p,c,i,bi in entries]
