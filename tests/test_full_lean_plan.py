"""Full mathlib extraction plan must have complete, honest coverage."""
import json
import sqlite3
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.full_lean_plan import build_full_plan, partition_batches
from math_mcts.source_registry import SOURCE_COMMIT
from tools.generate_full_lean_batch import generate_batch_script


class FullPlanTests(unittest.TestCase):
    def fixture(self,tmp):
        db=Path(tmp)/"index.sqlite"
        fixture_db(db)
        with sqlite3.connect(db) as cx:
            cx.execute("UPDATE source_registry SET imported_commit=?",
                       (SOURCE_COMMIT,))
        return db

    def test_every_registered_theorem_in_plan_no_autocredit(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(td)
            out=Path(td)/"full.json"
            summary=build_full_plan(db,out,max_per_batch=1)
            self.assertEqual(summary["registered_total"],1)
            self.assertEqual(summary["scheduled_total"],1)
            self.assertEqual(summary["unsupported_total"],0)
            self.assertEqual(summary["execution_status"],"not_executed")
            plan=json.loads(out.read_text())
            self.assertEqual(plan["batch_count"],1)
            self.assertEqual(plan["batches"][0]["registered_declarations"][0]["source_id"],"MTH01")
            self.assertEqual(partition_batches(plan,worker=0,workers=2),plan["batches"])
            self.assertEqual(partition_batches(plan,worker=1,workers=2),[])
            script=Path(td)/"selected.lean"
            result=generate_batch_script(out,"B000000",script)
            text=script.read_text()
            self.assertEqual(result["selected"],1)
            self.assertIn("import Mathlib.Algebra.Group.Basic",text)
            self.assertNotIn("import Mathlib\n",text)
            self.assertIn('"source_statement_sha256"',text)

    def test_unsupported_names_remain_explicit_not_lost(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(td)
            with sqlite3.connect(db) as cx:
                raw=json.loads(cx.execute("SELECT record FROM documents WHERE id='MTH01'").fetchone()[0])
                raw["en"]="∀invalid"
                raw["formal"]="theorem ∀invalid : True := trivial"
                cx.execute("UPDATE documents SET record=? WHERE id='MTH01'",(json.dumps(raw),))
            p=Path(td)/"plan.json"
            status=build_full_plan(db,p)
            self.assertEqual(status["registered_total"],1)
            self.assertEqual(status["scheduled_total"],0)
            self.assertEqual(status["unsupported_total"],1)
            self.assertEqual(status["reason_counts"]["unsupported_declaration_syntax"],1)

    def test_tampered_statement_fails_early(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(td)
            with sqlite3.connect(db) as cx:
                raw=json.loads(cx.execute("SELECT record FROM documents WHERE id='MTH01'").fetchone()[0])
                raw["formal"]="theorem smul_theorem : False := trivial"
                cx.execute("UPDATE documents SET record=? WHERE id='MTH01'",(json.dumps(raw),))
            with self.assertRaisesRegex(ValueError,"corrupted"):
                build_full_plan(db,Path(td)/"plan.json")

    def test_corrupted_batch_fingerprint_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            db=self.fixture(td)
            p=Path(td)/"plan.json"
            build_full_plan(db,p)
            data=json.loads(p.read_text())
            data["batches"][0]["registered_declarations"][0]["source_id"]="forged"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"fingerprint"):
                generate_batch_script(p,"B000000",Path(td)/"Selected.lean")


if __name__=="__main__":
    unittest.main()
