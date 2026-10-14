"""Strict matching of Lean exported expression references to registered mathlib."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge
from math_mcts.lean_reference_index import (LeanReferenceGraph,
                                            import_lean_exports)
from math_mcts.source_registry import SOURCE_COMMIT


class LeanReferenceTests(unittest.TestCase):
    def setup_index(self, folder):
        db=Path(folder)/"math.sqlite"
        fixture_db(db)
        with sqlite3.connect(db) as cx:
            row=json.loads(cx.execute("SELECT record FROM documents WHERE "
                                      "id='MTH01'").fetchone()[0])
            row['id']='MTH02'
            row['en']='smul_other'
            row['formal']='theorem smul_other : True := trivial'
            import hashlib
            fingerprint=hashlib.sha256(b': True := trivial').hexdigest()
            row['original_metadata']['陈述SHA256']=fingerprint
            cx.execute("INSERT INTO documents VALUES (?,?,?,?,?)",
                       ("MTH02","unreviewed_import",5,"Algebra",json.dumps(row)))
            # Original MTH01 happens to have same statement fingerprint in the
            # synthetic fixture. This test avoids a uniqueness policy because
            # only the source registry's ID is used for foreign-key linkage.
            cx.execute("INSERT INTO source_registry VALUES(?,?,?,?,?,?)",
                       ("MTH02",fingerprint,row['module'],"fixed-commit",
                        "unreviewed_importance",None))
            cx.execute("UPDATE source_registry SET imported_commit=?",
                       (SOURCE_COMMIT,))
        classify_knowledge(db)
        return db

    def export(self, db, outfile):
        with sqlite3.connect(db) as cx:
            sha=cx.execute("SELECT source_sha256 FROM source_registry "
                           "WHERE id='MTH01'").fetchone()[0]
        records=[
            {"source_id":"MTH01","declaration":"Mathlib.Algebra.Group.Basic.smul_theorem",
             "module":"Mathlib.Algebra.Group.Basic",
             "mathlib_commit":SOURCE_COMMIT,"source_statement_sha256":sha,
             "type_expression":"∀ x, demo_true x",
             "type_references":["Mathlib.Algebra.Group.Basic.smul_other","Eq"],
             "proof_references":["Mathlib.Algebra.Group.Basic.smul_other"],
             "lean_version":"Lean 4.34.0"},
            {"source_id":"MTH02","declaration":"Mathlib.Algebra.Group.Basic.smul_other",
             "module":"Mathlib.Algebra.Group.Basic",
             "mathlib_commit":SOURCE_COMMIT,"source_statement_sha256":sha,
             "type_expression":"True",
             "type_references":["True"],
             "proof_references":["True.intro"],
             "lean_version":"Lean 4.34.0"},
        ]
        outfile.write_text("".join(json.dumps(r)+"\n" for r in records))
        return records

    def test_import_exact_source_declarations_and_reverse_references(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.setup_index(folder)
            source=Path(folder)/"lean_export.jsonl"
            self.export(db,source)
            report=import_lean_exports(db,source)
            self.assertEqual(report['matched_registered_theorems'],2)
            self.assertEqual(report['evidence_status'],'external_export_unattested')
            g=LeanReferenceGraph(db)
            refs=g.references('MTH01')
            self.assertIn({'constant':'Mathlib.Algebra.Group.Basic.smul_other',
                           'relation':'elaborated_type_reference',
                           'status':'syntactic_reference_not_inference'},refs)
            back=g.backward_dependencies('MTH01',max_hops=2)
            self.assertEqual(back['reachable_declarations'],2)
            self.assertTrue(any(r['dependency']=='MTH02'
                                for r in back['references']))
            with sqlite3.connect(db) as cx:
                self.assertEqual(cx.execute("SELECT COUNT(*) FROM "
                    "lean_declaration_export WHERE evidence_status="
                    "'external_export_unattested'").fetchone()[0],2)

    def test_invalid_identity_or_commit_rejected_before_publishing(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.setup_index(folder)
            source=Path(folder)/"lean_export.jsonl"
            records=self.export(db,source)
            cases=[
                ('mathlib_commit','0'*40),
                ('module','Mathlib.Data.List.Basic'),
                ('source_statement_sha256','bad'),
                ('declaration','Other.unrelated'),
            ]
            for field,value in cases:
                with self.subTest(field=field):
                    mutated=json.loads(json.dumps(records))
                    mutated[0][field]=value
                    source.write_text("".join(json.dumps(x)+"\n" for x in mutated))
                    with self.assertRaises(ValueError):
                        import_lean_exports(db,source)
                    with sqlite3.connect(db) as cx:
                        exists=cx.execute("SELECT name FROM sqlite_master WHERE "
                                          "name='lean_declaration_export'").fetchone()
                        self.assertIsNone(exists)

    def test_duplicate_references_and_oversized_entries_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.setup_index(folder)
            source=Path(folder)/"lean_export.jsonl"
            records=self.export(db,source)
            records[0]["type_references"]=["Eq","Eq"]
            source.write_text("".join(json.dumps(x)+"\n" for x in records))
            with self.assertRaisesRegex(ValueError,"Duplicate Lean references"):
                import_lean_exports(db,source)
            source.write_text("x"*1_000_001+"\n")
            with self.assertRaisesRegex(ValueError,"Oversized"):
                import_lean_exports(db,source)

    def test_export_cannot_be_trusted_as_kernel_evidence_by_json(self):
        with tempfile.TemporaryDirectory() as folder:
            db=self.setup_index(folder)
            source=Path(folder)/"lean_export.jsonl"
            records=self.export(db,source)
            records[0]["verified_by_kernel"]=True
            source.write_text("".join(json.dumps(x)+"\n" for x in records))
            import_lean_exports(db,source)
            with sqlite3.connect(db) as cx:
                status=cx.execute("SELECT evidence_status FROM "
                                  "lean_declaration_export WHERE id='MTH01'").fetchone()[0]
            self.assertEqual(status,"external_export_unattested")

if __name__=="__main__":
    unittest.main()
