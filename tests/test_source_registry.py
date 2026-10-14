"""Registration is a mechanical source check, never an importance judgment."""
import gzip
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math_mcts.fast_index import fast_search
from math_mcts.source_registry import (
    register_source_statements, get_registered_statement, SOURCE_COMMIT)


def row(i, *, good=True):
    name = f"upstream_{i}"
    formal = f"theorem {name} : True := trivial"
    digest = hashlib.sha256(formal.removeprefix("theorem " + name).strip()
                            .encode()).hexdigest()
    return {
        "id": f"I{i}", "en": name, "module": "Mathlib.Algebra.Example",
        "formal": formal, "level": 5, "tags": ["unreviewed"],
        "original_metadata": {
            "类型": "upstream_theorem",
            "陈述SHA256": digest if good else "0" * 64
        },
    }


class SourceRegistryTests(unittest.TestCase):
    def make_db(self, path):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT INTO metadata VALUES('schema','1')")
            db.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, tier TEXT NOT NULL, "
                       "level INTEGER, domain TEXT NOT NULL, record TEXT NOT NULL)")
            for record in [row(1), row(2, good=False)]:
                db.execute("INSERT INTO documents VALUES (?,?,?,?,?)",
                           (record["id"], "unreviewed_import", None, "Algebra",
                            json.dumps(record)))

    def test_registers_only_source_integrity_not_importance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "i.sqlite"
            manifest = Path(tmp) / "registered.jsonl.gz"
            self.make_db(db)
            report = register_source_statements(db, manifest)
            self.assertEqual(report["candidate_count"], 2)
            self.assertEqual(report["formally_registered_source_statements"], 1)
            self.assertEqual(report["rejected_count"], 1)
            self.assertEqual(report["rejection_reasons"], {
                "original_statement_hash_mismatch": 1})
            self.assertEqual(report["mathematical_importance_reviewed_count"], 0)
            hit = get_registered_statement(db, "I1")
            self.assertEqual(hit["source_commit"], SOURCE_COMMIT)
            self.assertIsNone(hit["level"])
            self.assertEqual(hit["importance_status"], "unreviewed")
            self.assertIsNone(get_registered_statement(db, "I2"))
            with gzip.open(manifest, "rt") as f:
                item = json.loads(f.readline())
                self.assertTrue(item["registered_statement"])
                self.assertFalse(item["reviewed_importance"])
                self.assertFalse(item["proof_verified_this_run"])
                self.assertFalse(f.readline())

    def test_search_only_registered_through_fts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "i.sqlite"
            self.make_db(db)
            with sqlite3.connect(db) as cx:
                cx.execute("CREATE VIRTUAL TABLE term_index USING fts5(terms)")
                for (rid,) in cx.execute("SELECT rowid FROM documents"):
                    cx.execute("INSERT INTO term_index(rowid,terms) VALUES (?,?)",
                               (rid, "upstream"))
            register_source_statements(db, Path(tmp) / "registered.gz")
            matches = fast_search(db, "upstream", registered_only=True)
            self.assertEqual([x["id"] for x in matches], ["I1"])

    def test_repeat_registration_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "i.sqlite"
            manifest = Path(tmp) / "reg.gz"
            self.make_db(db)
            register_source_statements(db, manifest)
            result = register_source_statements(db, manifest)
            self.assertEqual(result["formally_registered_source_statements"], 1)

    def test_unknown_index_schema_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "empty.sqlite"
            with sqlite3.connect(db):
                pass
            with self.assertRaisesRegex(ValueError, "metadata"):
                register_source_statements(db, Path(tmp) / "reg.gz")


if __name__ == "__main__":
    unittest.main()
