"""Regression tests for evidence-only mathematics quality triage."""
import json
import sqlite3
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge
from math_mcts.review_quality import normalized_name, review_signals, review_queue


def add_record(conn, id, name, formula, module):
    row = {"id": id, "en": name, "cn": name, "formal": formula,
           "module": module, "domain_en": module.split(".")[1],
           "level": 5, "original_metadata": {
               "类型": "upstream_theorem", "陈述SHA256": "synthetic-" + id}}
    conn.execute("INSERT INTO documents VALUES(?,?,?,?,?)",
                 (id, "unreviewed_import", 5, row["domain_en"],
                  json.dumps(row, ensure_ascii=False)))
    conn.execute("INSERT INTO source_registry VALUES (?,?,?,?,?,?)",
                 (id, "synthetic-" + id, module, "fixed-commit",
                  "unreviewed_importance", None))


class ReviewQualityTests(unittest.TestCase):
    def prepare(self, tmp):
        path = Path(tmp) / "knowledge.sqlite"
        fixture_db(path)
        with sqlite3.connect(path) as db:
            # One exact title match anchors MTH01 to an *existing title*,
            # with no claim of mathematical equivalence.
            base = json.loads(db.execute(
                "SELECT record FROM documents WHERE id='CUR01'").fetchone()[0])
            base["en"] = "smul_theorem"
            db.execute("UPDATE documents SET record=? WHERE id='CUR01'",
                       (json.dumps(base, ensure_ascii=False),))
            add_record(db, "MTH02", "smul_theorem",
                       "theorem smul_theorem : True := trivial",
                       "Mathlib.Analysis.Basic")
            add_record(db, "MTH03", "special_lemma",
                       "theorem special_lemma : True := sorry",
                       "Mathlib.CategoryTheory.Example")
        classify_knowledge(path)
        return path

    def test_all_rows_signaled_without_auto_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.prepare(tmp)
            report = review_signals(path)
            self.assertEqual(report["source_knowledge_scanned"], 4)
            self.assertEqual(report["importance_or_level_promoted"], 0)
            self.assertEqual(report["same_name_group_members"], 2)
            self.assertEqual(report["same_statement_group_members"], 2)
            self.assertEqual(report["reason_counts"]["placeholder_keyword_in_source_text"], 1)
            self.assertEqual(report["reason_counts"]["lexical_name_matches_curated"], 2)
            picks = review_queue(path, mode="priority", limit=10)
            self.assertEqual(len(picks), 4)
            self.assertEqual(picks[0]["review_bucket"], "curated_title_review")
            self.assertEqual(picks[0]["importance_status"], "unassessed")
            anomalies = review_queue(path, mode="anomaly", limit=1)
            self.assertEqual(anomalies[0]["id"], "MTH03")
            with sqlite3.connect(path) as db:
                bad = db.execute("SELECT COUNT(*) FROM classified_knowledge "
                                 "WHERE source_tier='unreviewed_import' "
                                 "AND (difficulty_level IS NOT NULL OR "
                                 "importance_status!='importance_unrated')").fetchone()[0]
                self.assertEqual(bad, 0)
            self.assertEqual(report, review_signals(path))

    def test_raw_identifier_similarity_does_not_merge_definitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.prepare(tmp)
            review_signals(path)
            with sqlite3.connect(path) as db:
                count = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                self.assertEqual(count, 5)
                count = db.execute("SELECT COUNT(*) FROM knowledge_review_signals").fetchone()[0]
                self.assertEqual(count, 4)

    def test_invalid_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.prepare(tmp)
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM classified_knowledge WHERE id='MTH02'")
            with self.assertRaisesRegex(RuntimeError, "coverage"):
                review_signals(path)

    def test_pagination_mode_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.prepare(tmp)
            review_signals(path)
            with self.assertRaises(ValueError):
                review_queue(path, mode="nonexistent")
            with self.assertRaises(ValueError):
                review_queue(path, limit=0)
            with self.assertRaises(ValueError):
                review_queue(path, offset=-1)

    def test_normalize_name_is_lexical_only(self):
        self.assertEqual(normalized_name("Matrix_Theory"), "matrixtheory")
        self.assertNotEqual(normalized_name("MatrixLemma"),
                            normalized_name("MatrixTheorem"))


if __name__ == "__main__":
    unittest.main()
