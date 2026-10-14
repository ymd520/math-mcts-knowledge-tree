"""Semantic type metadata ingestion cannot invent verified mathematical rules."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge
from math_mcts.source_registry import SOURCE_COMMIT
from math_mcts.full_lean_plan import build_full_plan
from math_mcts.full_lean_import import ingest_full_receipts,indexed_type_conditions


class FullTypeImportTests(unittest.TestCase):
    def prepare(self,tmp):
        db=Path(tmp)/"db.sqlite"
        fixture_db(db)
        with sqlite3.connect(db) as cx:
            cx.execute("UPDATE source_registry SET imported_commit=?",(SOURCE_COMMIT,))
        classify_knowledge(db)
        p=Path(tmp)/"plan.json"
        build_full_plan(db,p)
        batch=json.loads(p.read_text())["batches"][0]
        d=Path(tmp)/"out"
        d.mkdir()
        row={
            "source_id":"MTH01","declaration":"Mathlib.Algebra.Group.Basic.smul_theorem",
            "module":"Mathlib.Algebra.Group.Basic",
            "mathlib_commit":SOURCE_COMMIT,
            "source_statement_sha256":batch["registered_declarations"][0]["source_statement_sha256"],
            "type_expression":"∀ (x : Nat), True",
            "leading_pi_binders":1,"elaborated_type_head":"forallE",
            "type_references":["Nat"],"proof_references":["True.intro"],
            "lean_version":"pinned-mathlib-toolchain",
            "verified_by_kernel":True,  # intentionally untrusted flag
        }
        blob=json.dumps(row)+"\n"
        (d/(batch["batch_id"]+".jsonl")).write_text(blob)
        receipt={
            "batch_id":batch["batch_id"],"batch_sha256":batch["batch_sha256"],
            "module":batch["module"],"source_commit":SOURCE_COMMIT,
            "expected_ids":["MTH01"],"status":"executed",
            "exported_ids":["MTH01"],"missing_ids":[],
            "github_run_id":"synthetic-no-kernel",
            "export_sha256":hashlib.sha256(blob.encode()).hexdigest(),
        }
        (d/(batch["batch_id"]+".receipt.json")).write_text(json.dumps(receipt))
        return db,p,d

    def test_type_profile_is_syntactic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,plan,dir=self.prepare(tmp)
            first=ingest_full_receipts(db,plan,dir)
            self.assertEqual(first["new_source_matched_entries"],1)
            self.assertEqual(first["evidence_status"],"external_export_unattested")
            self.assertEqual(first["reviewed_math_implications"],0)
            info=indexed_type_conditions(db,"MTH01")
            self.assertEqual(info["leading_pi_binders"],1)
            self.assertEqual(info["elaborated_type_head"],"forallE")
            self.assertFalse(info["logical_assumptions_verified"])
            self.assertFalse(info["usable_as_horn_rule"])
            second=ingest_full_receipts(db,plan,dir)
            self.assertEqual(second["idempotent_entries"],1)
            self.assertEqual(second["total_stored_entries"],1)
            with sqlite3.connect(db) as cx:
                self.assertEqual(cx.execute(
                    "SELECT COUNT(*) FROM lean_full_references").fetchone()[0],2)

    def test_edited_type_rejected_when_existing_data_would_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,plan,folder=self.prepare(tmp)
            ingest_full_receipts(db,plan,folder)
            export=next(folder.glob("*.jsonl"))
            data=json.loads(export.read_text())
            data["type_expression"]="False"
            blob=json.dumps(data)+"\n"
            export.write_text(blob)
            receipt_file=next(folder.glob("*.receipt.json"))
            receipt=json.loads(receipt_file.read_text())
            receipt["export_sha256"]=hashlib.sha256(blob.encode()).hexdigest()
            receipt_file.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,"Conflicting"):
                ingest_full_receipts(db,plan,folder)


if __name__=="__main__":
    unittest.main()
