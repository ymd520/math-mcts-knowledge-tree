"""Strictly audit source-wide extraction receipts without conflating plans/proofs."""
import hashlib
import json
import sqlite3
import tempfile
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.source_registry import SOURCE_COMMIT
from math_mcts.full_lean_plan import build_full_plan
from math_mcts.full_lean_coverage import audit_full_extraction


class CoverageTests(unittest.TestCase):
    def test_partial_cannot_pass_full_certification(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"db.sqlite"
            fixture_db(path)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE source_registry SET imported_commit=?",(SOURCE_COMMIT,))
            plan=Path(td)/"plan.json"
            build_full_plan(path,plan)
            root=Path(td)/"receipts"
            root.mkdir()
            status=audit_full_extraction(plan,root)
            self.assertEqual(status["registered_total"],1)
            self.assertEqual(status["not_run_declarations"],1)
            self.assertFalse(status["complete"])
            with self.assertRaisesRegex(RuntimeError,"NOT COMPLETE"):
                audit_full_extraction(plan,root,require_complete=True)

    def test_receipt_requires_real_matching_export_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"db.sqlite"
            fixture_db(path)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE source_registry SET imported_commit=?",(SOURCE_COMMIT,))
            plan_file=Path(td)/"plan.json"
            build_full_plan(path,plan_file)
            batch=json.loads(plan_file.read_text())["batches"][0]
            root=Path(td)/"receipts"
            root.mkdir()
            bid=batch["batch_id"]
            exported=[{"source_id":"MTH01","declaration":"smul_theorem",
                       "module":"Mathlib.Algebra.Group.Basic",
                       "type_expression":"True", "type_references":[],
                       "proof_references":[]}]
            exported_file=root/(bid+".jsonl")
            exported_file.write_text("".join(json.dumps(e)+"\n" for e in exported))
            receipt={
                "batch_id":bid,"batch_sha256":batch["batch_sha256"],
                "module":batch["module"],"source_commit":SOURCE_COMMIT,
                "expected_ids":["MTH01"],"status":"executed",
                "exported_ids":["MTH01"],"missing_ids":[],
                "export_sha256":hashlib.sha256(exported_file.read_bytes()).hexdigest(),
            }
            (root/(bid+".receipt.json")).write_text(json.dumps(receipt))
            result=audit_full_extraction(plan_file,root)
            self.assertTrue(result["complete"])
            exported_file.write_text("{}\n")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                audit_full_extraction(plan_file,root)

    def test_failed_receipt_cannot_claim_any_success(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"db.sqlite"
            fixture_db(db)
            with sqlite3.connect(db) as cx:
                cx.execute("UPDATE source_registry SET imported_commit=?",(SOURCE_COMMIT,))
            p=Path(td)/"p.json";build_full_plan(db,p)
            b=json.loads(p.read_text())["batches"][0]
            root=Path(td)/"r";root.mkdir()
            (root/(b["batch_id"]+".receipt.json")).write_text(json.dumps({
                "batch_id":b["batch_id"],"batch_sha256":b["batch_sha256"],
                "source_commit":SOURCE_COMMIT,"expected_ids":["MTH01"],
                "status":"worker_error","exported_ids":["MTH01"],"missing_ids":[]}))
            with self.assertRaisesRegex(ValueError,"Failed batch"):
                audit_full_extraction(p,root)


if __name__=="__main__":
    unittest.main()
