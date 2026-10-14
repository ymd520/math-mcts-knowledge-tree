"""Human editorial gate requires precise source and independent grade."""
import sqlite3
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge
from math_mcts.editorial import apply_review_decisions,reviewer_coverage


class EditorialTests(unittest.TestCase):
    def setup_database(self,tmp):
        path=Path(tmp)/"math.sqlite"
        fixture_db(path)
        classify_knowledge(path)
        with sqlite3.connect(path) as db:
            sha=db.execute("SELECT source_sha256 FROM source_registry "
                           "WHERE id='MTH01'").fetchone()[0]
        return path,sha

    def decision(self,sha):
        return {"id":"MTH01","source_sha256":sha,"importance":"important",
                "level":3,"importance_reason":"Explicitly reviewed reuse in algebra",
                "grade_reason":"Requires abstract algebra definitions",
                "reference_locator":"Mathlib.Algebra.Group.Basic:smul_theorem",
                "reviewer":"Fixture reviewer", "reviewed_on":"2026-10-14"}

    def test_review_is_logged_without_editing_imported_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,sha=self.setup_database(tmp)
            report=apply_review_decisions(db,[self.decision(sha)])
            self.assertEqual(report["decisions_written"],1)
            coverage=reviewer_coverage(db)
            self.assertEqual(coverage["explicit_review_decisions"],1)
            with sqlite3.connect(db) as cx:
                row=cx.execute("SELECT importance_status,difficulty_level "
                               "FROM classified_knowledge WHERE id='MTH01'").fetchone()
                self.assertEqual(row,("importance_unrated",None))

    def test_stale_hash_and_missing_reviewer_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,sha=self.setup_database(tmp)
            bad=self.decision("0"*64)
            with self.assertRaisesRegex(ValueError,"stale"):
                apply_review_decisions(db,[bad])
            bad=self.decision(sha)
            bad["reviewer"]=""
            with self.assertRaisesRegex(ValueError,"reviewer"):
                apply_review_decisions(db,[bad])
            self.assertEqual(reviewer_coverage(db)["explicit_review_decisions"],0)

    def test_changed_theorem_after_registry_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,sha=self.setup_database(tmp)
            with sqlite3.connect(db) as cx:
                record=json.loads(cx.execute("SELECT record FROM documents "
                        "WHERE id='MTH01'").fetchone()[0])
                record["formal"]="theorem smul_theorem : False := sorry"
                cx.execute("UPDATE documents SET record=? WHERE id='MTH01'",
                           (json.dumps(record),))
            with self.assertRaisesRegex(ValueError,"changed"):
                apply_review_decisions(db,[self.decision(sha)])

    def test_invalid_grade_and_unknown_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,sha=self.setup_database(tmp)
            bad=self.decision(sha);bad["level"]=None
            with self.assertRaisesRegex(ValueError,"level"):
                apply_review_decisions(db,[bad])
            bad=self.decision(sha);bad["id"]="NO_SUCH_ID"
            with self.assertRaisesRegex(ValueError,"Only source-registered"):
                apply_review_decisions(db,[bad])


if __name__=="__main__":
    unittest.main()
