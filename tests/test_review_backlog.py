"""Every registered theorem must retain original provenance and human audit status."""
import gzip
import json
import sqlite3
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge
from math_mcts.review_backlog import export_review_backlog


class BacklogTests(unittest.TestCase):
    def test_full_review_backlog_without_misattribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"db.sqlite"
            fixture_db(db)
            classify_knowledge(db)
            path=Path(tmp)/"backlog.jsonl.gz"
            report=export_review_backlog(db,path)
            self.assertEqual(report["source_records"],1)
            self.assertEqual(report["not_human_reviewed"],1)
            self.assertEqual(report["reviewed_important"],0)
            with gzip.open(path,"rt",encoding="utf-8") as f:
                rows=[json.loads(l) for l in f]
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["importance"],"unassessed")
            self.assertIsNone(rows[0]["difficulty_level"])
            self.assertEqual(rows[0]["source"]["license"],"Apache-2.0")
            self.assertEqual(rows[0]["source"]["mathematics_originality_claim"],"none")
            self.assertFalse(rows[0]["mathematical_conditions_approved"])
            self.assertEqual(export_review_backlog(db,path),report)


if __name__=="__main__":
    unittest.main()
