"""Data-backed tests for three independent knowledge classification axes."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.fast_index import terms_for
from math_mcts.knowledge_bank import KnowledgeBank, classify_knowledge


def fixture_db(path):
    rows = [
        {"id": "CUR01", "cn": "集合的并", "en": "Set union",
         "definition": "集合并运算", "level": 2, "tags": ["重要"],
         "kind": "概念", "domain_cn": "数学基础", "domain_en": "Foundations",
         "branch_cn": "集合论", "topic_cn": "基础运算", "module": ""},
        {"id": "MTH01", "cn": "mathlib example", "en": "smul_theorem",
         "formal": "theorem smul_theorem : True := trivial", "level": 5,
         "module": "Mathlib.Algebra.Group.Basic", "domain_en": "Algebra",
         "domain_cn": "Algebra", "original_metadata": {
             "类型": "upstream_theorem", "陈述SHA256": "testsha"}},
        {"id": "STD01", "cn": "标准知识卡", "en": "standard",
         "definition": "有限集合的定义", "level": 5,
         "module": "Mathlib.Data.Finset.Basic", "domain_en": "Data",
         "original_metadata": {"类型": "curated_standard_card",
                               "陈述SHA256": "referencehash"}},
    ]
    with sqlite3.connect(str(path)) as db:
        db.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, tier TEXT, "
                   "level INTEGER, domain TEXT, record TEXT)")
        db.execute("CREATE VIRTUAL TABLE term_index USING fts5(terms)")
        db.execute("CREATE TABLE source_registry "
                   "(id TEXT PRIMARY KEY, source_sha256 TEXT, module TEXT, "
                   "imported_commit TEXT, importance_status TEXT, level INTEGER)")
        for i, row in enumerate(rows, 1):
            tier = "curated" if i == 1 else "unreviewed_import"
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?)",
                       (row["id"], tier, row["level"],
                        row.get("domain_en", ""), json.dumps(row, ensure_ascii=False)))
            searchtext = " ".join(str(row.get(f, "")) for f in
                                  ("cn", "en", "definition", "formal", "module"))
            db.execute("INSERT INTO term_index(rowid,terms) VALUES (?,?)",
                       (i, " ".join(terms_for(searchtext))))
        db.execute("INSERT INTO source_registry VALUES(?,?,?,?,?,?)",
                   ("MTH01", "testsha", "Mathlib.Algebra.Group.Basic",
                    "fixed-commit", "unreviewed_importance", None))


class KnowledgeClassificationTests(unittest.TestCase):
    def test_complete_three_axis_classification(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.sqlite"
            fixture_db(path)
            report = classify_knowledge(path)
            self.assertEqual(report["total_knowledge_records"], 3)
            self.assertEqual(report["source_knowledge_imported"], 2)
            self.assertEqual(report["source_registered_theorems"], 1)
            self.assertEqual(report["source_standard_cards_pending"], 1)
            self.assertEqual(report["importance_unrated_new_source_records"], 2)
            bank = KnowledgeBank(path)
            theorem = bank.get("MTH01")
            self.assertEqual(theorem["domain"], "代数")
            self.assertEqual(theorem["kind"], "定理声明")
            self.assertEqual(theorem["difficulty_level"], None)
            self.assertEqual(theorem["importance_status"], "importance_unrated")
            self.assertEqual(theorem["registration_status"],
                             "source_statement_registered")
            self.assertEqual(theorem["source_subfield"], "Algebra")
            standard = bank.get("STD01")
            self.assertEqual(standard["registration_status"],
                             "standard_card_source_pending")
            self.assertEqual(standard["domain"], "计算与优化")
            curated = bank.get("CUR01")
            self.assertEqual(curated["difficulty_level"], 2)
            self.assertEqual(curated["importance_status"], "existing_important_tag")
            self.assertEqual(len(bank.browse(domain="代数")), 1)
            self.assertEqual(bank.search("smul", kind="定理声明")[0]["id"], "MTH01")
            self.assertEqual(bank.search("smul", domain="数学基础"), [])
            self.assertEqual([r["id"] for r in bank.browse(limit=2)], ["CUR01", "MTH01"])
            self.assertEqual([r["id"] for r in
                              bank.browse(after_id="MTH01", limit=5)], ["STD01"])
            # Rebuilding the view is stable and does not modify source data.
            self.assertEqual(report, classify_knowledge(path))

    def test_registry_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.sqlite"
            with sqlite3.connect(str(path)) as db:
                db.execute("CREATE TABLE documents "
                           "(id TEXT PRIMARY KEY, tier TEXT, record TEXT)")
            with self.assertRaisesRegex(ValueError, "registration"):
                classify_knowledge(path)

    def test_unregistered_theorem_not_silently_classified_as_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.sqlite"
            fixture_db(path)
            with sqlite3.connect(str(path)) as db:
                db.execute("DELETE FROM source_registry")
            with self.assertRaisesRegex(ValueError, "Unverified theorem"):
                classify_knowledge(path)

    def test_browse_limits_are_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "knowledge.sqlite"
            fixture_db(path)
            classify_knowledge(path)
            with self.assertRaises(ValueError):
                KnowledgeBank(path).browse(limit=0)
            with self.assertRaises(ValueError):
                KnowledgeBank(path).search("set", top_k=501)


if __name__ == "__main__":
    unittest.main()
