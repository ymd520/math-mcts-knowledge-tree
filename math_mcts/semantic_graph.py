"""Source-bound, *typed reviewed-rule* semantic adjacency graph.

Graph vertices are reviewed Horn rules, not 100k text-only mathlib statements.
An edge asserts that a producer conclusion can unify with a specific consumer
premise under the RuleBook's predicate sorts and equality constraints. This
does NOT assert a proof: remaining premises must still be demonstrated.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .reasoning import RuleBook
from .semantic_links import compatible_atoms


SCHEMA = "1"


def _edge_rows(book: RuleBook):
    # Index premise occurrences by the complete, typed predicate signature.
    # The RuleBook has already validated all rule terms and provenance.
    premise_index: dict[tuple, list] = {}
    for consumer in sorted(book.rules.values(), key=lambda r: r.id):
        for idx, atom in enumerate(consumer.premises):
            signature = (atom.predicate, book.signatures[atom.predicate])
            premise_index.setdefault(signature, []).append((consumer, idx, atom))
    for producer in sorted(book.rules.values(), key=lambda r: r.id):
        key = (producer.conclusion.predicate,
               book.signatures[producer.conclusion.predicate])
        for consumer, idx, atom in premise_index.get(key, ()):
            if producer.id == consumer.id:
                continue
            if not compatible_atoms(producer.conclusion, atom):
                continue
            remaining = [asdict(p) for i, p in enumerate(consumer.premises)
                         if i != idx]
            yield (producer.id, consumer.id, idx, atom.predicate,
                   json.dumps(book.signatures[atom.predicate], ensure_ascii=False),
                   len(remaining),
                   json.dumps(remaining, ensure_ascii=False, sort_keys=True),
                   "typed_possible_composition_not_proof")


def build_semantic_graph(book: RuleBook, path: str | Path) -> dict:
    """Atomic schema build; only explicitly reviewed rules are searchable."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".building")
    temp.unlink(missing_ok=True)
    conn = sqlite3.connect(str(temp))
    try:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("""CREATE TABLE rules (
            id TEXT PRIMARY KEY, conclusion_predicate TEXT NOT NULL,
            source TEXT NOT NULL, concept_id TEXT NOT NULL,
            concept_sha256 TEXT NOT NULL, body_json TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE edges (
            producer TEXT NOT NULL, consumer TEXT NOT NULL,
            consumer_premise_index INTEGER NOT NULL,
            predicate TEXT NOT NULL, signature TEXT NOT NULL,
            remaining_premise_count INTEGER NOT NULL,
            remaining_premises TEXT NOT NULL, validity TEXT NOT NULL,
            PRIMARY KEY (producer, consumer, consumer_premise_index),
            FOREIGN KEY (producer) REFERENCES rules(id),
            FOREIGN KEY (consumer) REFERENCES rules(id))""")
        for r in sorted(book.rules.values(), key=lambda r: r.id):
            conn.execute("INSERT INTO rules VALUES (?,?,?,?,?,?)",
                         (r.id, r.conclusion.predicate, r.source,
                          r.concept_id, r.concept_sha256,
                          json.dumps(asdict(r), ensure_ascii=False, sort_keys=True)))
        count = 0
        for edge in _edge_rows(book):
            conn.execute("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?)", edge)
            count += 1
        conn.execute("CREATE INDEX edges_by_consumer ON edges(consumer,predicate)")
        conn.execute("CREATE INDEX edges_by_predicate ON edges(predicate,producer)")
        conn.execute("CREATE INDEX rules_by_conclusion ON rules(conclusion_predicate)")
        conn.executemany("INSERT INTO metadata VALUES (?,?)", [
            ("schema", SCHEMA), ("rulebook_sha256", book.fingerprint()),
            ("reviewed_rules", str(len(book.rules))), ("composition_edges", str(count)),
            ("proof_status", "none: potential inference links only"),
        ])
        conn.commit()
        conn.close()
        os.replace(temp, output)
    except Exception:
        conn.close()
        temp.unlink(missing_ok=True)
        raise
    return {"reviewed_rules": len(book.rules), "candidate_edges": count,
            "rulebook_sha256": book.fingerprint(),
            "status": "typed_possible_composition_not_proof"}


class SemanticGraph:
    """Small, indexed on-disk neighborhood queries over reviewed inference rules."""

    def __init__(self, path: str | Path, *, book: RuleBook | None = None):
        self.path = Path(path)
        with sqlite3.connect(str(self.path)) as db:
            meta = dict(db.execute("SELECT key,value FROM metadata"))
        if meta.get("schema") != SCHEMA:
            raise ValueError("Unsupported graph schema")
        if book is not None and meta.get("rulebook_sha256") != book.fingerprint():
            raise ValueError("Semantic graph is stale relative to reviewed rulebook")
        self.metadata = meta

    def neighbors(self, rule_id: str, *, direction: str = "forward",
                  limit: int = 100) -> list[dict]:
        if direction not in {"forward", "backward"}:
            raise ValueError("direction must be forward/backward")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be 1..1000")
        col = "producer" if direction == "forward" else "consumer"
        with sqlite3.connect(str(self.path)) as db:
            records = db.execute(
                f"SELECT producer,consumer,consumer_premise_index,predicate,"
                f"signature,remaining_premise_count,remaining_premises,validity "
                f"FROM edges WHERE {col}=? ORDER BY producer,consumer,"
                f"consumer_premise_index LIMIT ?", (rule_id,limit)).fetchall()
        return [{"producer": a, "consumer": b, "premise_index": i,
                 "predicate": p, "signature": json.loads(sig),
                 "other_premises": k, "remaining_premises": json.loads(rem),
                 "status": val} for a,b,i,p,sig,k,rem,val in records]

    def backward_relevant_rules(self, book: RuleBook, goal_predicate: str) -> list[str]:
        """Conservative predicate reachability; cannot certify a theorem."""
        if self.metadata["rulebook_sha256"] != book.fingerprint():
            raise ValueError("Graph fingerprint mismatch")
        return [r.id for r in book.backward_rules(
            __import__("math_mcts.reasoning", fromlist=["Atom"]).Atom(
                goal_predicate,
                tuple(next(iter(book.objects_by_sort.get(s, [])), "")
                      for s in book.signatures[goal_predicate]))
        ))] if False else _backward_predicates(book, goal_predicate)


def _backward_predicates(book: RuleBook, goal: str) -> list[str]:
    if goal not in book.signatures:
        raise ValueError("Unknown goal predicate")
    required = {goal}
    selected = set()
    changed = True
    while changed:
        changed = False
        for r in book.rules.values():
            if r.conclusion.predicate not in required:
                continue
            if r.id not in selected:
                selected.add(r.id)
                changed = True
            new = {x.predicate for x in r.premises} - required
            if new:
                required.update(new)
                changed = True
    return sorted(selected)
