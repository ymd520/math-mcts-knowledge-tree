"""Adversarial tests: exhaustive ID accounting, type shape provenance, and credits."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge
from math_mcts.source_registry import SOURCE_COMMIT
from math_mcts.lean_fullscale import plan_full_corpus,verify_manifest
from math_mcts.lean_type_semantics import (
    index_elaborated_type_structure,candidate_type_connections)
from math_mcts.mathlib_credit_index import index_module_authors,module_credit
from tools.run_mathlib_shard import run_shard


def prepare_db(folder):
    db=Path(folder)/"math.sqlite"
    fixture_db(db)
    with sqlite3.connect(db) as cx:
        row=json.loads(cx.execute("SELECT record FROM documents WHERE id='MTH01'").fetchone()[0])
        row["id"]="MTH02"
        row["en"]="other_lemma"
        row["formal"]="theorem other_lemma : True := trivial"
        cx.execute("INSERT INTO documents VALUES(?,?,?,?,?)",
                   ("MTH02","unreviewed_import",5,"Algebra",json.dumps(row)))
        sha=cx.execute("SELECT source_sha256 FROM source_registry WHERE id='MTH01'").fetchone()[0]
        cx.execute("INSERT INTO source_registry VALUES (?,?,?,?,?,?)",
                   ("MTH02",sha,row["module"],SOURCE_COMMIT,
                    "unreviewed_importance",None))
        cx.execute("UPDATE source_registry SET imported_commit=?",(SOURCE_COMMIT,))
    classify_knowledge(db)
    return db,sha


class FullCorpusTests(unittest.TestCase):
    def test_exhaustive_planning_and_dry_run_is_not_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,_=prepare_db(tmp)
            plan=Path(tmp)/"plan"
            result=plan_full_corpus(db,plan,shards=4,batch_size=1)
            self.assertEqual(result["registered_total"],2)
            self.assertEqual(result["renderable_total"],2)
            self.assertEqual(verify_manifest(plan,expected_total=2)["accounted"],2)
            target=next(x["shard"] for x in result["shards"] if x["candidate_count"])
            report=run_shard(plan,target,mathlib_root=Path(tmp),
                             output_root=Path(tmp)/"results",dry_run=True)
            self.assertEqual(report["extracted"],0)
            self.assertEqual(report["result_status"],"dry_run_only")
            self.assertGreater(report["remaining"],0)
            generated=list((Path(tmp)/"results").rglob("lean-batch-*.lean"))
            self.assertTrue(generated)
            content=generated[0].read_text()
            self.assertIn("import Mathlib.Algebra.Group.Basic",content)
            self.assertIn("mctsForallBinders info.type",content)
            self.assertIn("source_statement_sha256",content)

    def test_shard_tampering_cannot_be_counted_as_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,_=prepare_db(tmp)
            plan=Path(tmp)/"plan"
            data=plan_full_corpus(db,plan,shards=2,batch_size=3)
            shard=plan/data["shards"][0]["file"]
            shard.write_text(shard.read_text()+" ")
            with self.assertRaisesRegex(ValueError,"Tampered"):
                verify_manifest(plan)

    def test_bad_registry_fingerprint_refuses_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,_=prepare_db(tmp)
            with sqlite3.connect(db) as cx:
                cx.execute("UPDATE source_registry SET source_sha256='tampered' "
                           "WHERE id='MTH01'")
            with self.assertRaisesRegex(ValueError,"changed"):
                plan_full_corpus(db,Path(tmp)/"bad")


class TypeStructureTests(unittest.TestCase):
    def test_true_source_bound_ast_not_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,sha=prepare_db(tmp)
            base={"module":"Mathlib.Algebra.Group.Basic",
                  "mathlib_commit":SOURCE_COMMIT,
                  "source_statement_sha256":sha,
                  "type_structure_source":"actual_elaborated_lean_expr"}
            a={**base,"source_id":"MTH01","declaration":"Mathlib.Algebra.Group.Basic.smul_theorem",
               "type_binders":[],"conclusion_ast":"Expr.const P"}
            b={**base,"source_id":"MTH02","declaration":"Mathlib.Algebra.Group.Basic.other_lemma",
               "type_binders":[{"name":"h","domain_ast":"Expr.const P",
                                "domain_constants":["P"],"binder_info":"default"}],
               "conclusion_ast":"Expr.const Q"}
            file=Path(tmp)/"semantic.jsonl"
            file.write_text(json.dumps(a)+"\n"+json.dumps(b)+"\n")
            report=index_elaborated_type_structure(db,file)
            self.assertEqual(report["source_declarations_with_type_structure"],2)
            self.assertEqual(report["quantified_binders"],1)
            self.assertEqual(report["certified_applications"],0)
            links=candidate_type_connections(db)
            self.assertEqual(len(links),1)
            self.assertEqual(links[0]["proof_status"],
                             "no_proof_not_typechecked_as_application")
            bad=dict(a)
            bad["type_structure_source"]="assistant_guessed"
            file.write_text(json.dumps(bad)+"\n")
            with self.assertRaisesRegex(ValueError,"actual Lean"):
                index_elaborated_type_structure(db,file)


class SourceCreditTests(unittest.TestCase):
    def test_all_registered_theorems_link_to_pinned_file_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,_=prepare_db(tmp)
            root=Path(tmp)/"mathlib"
            path=root/"Mathlib/Algebra/Group/Basic.lean"
            path.parent.mkdir(parents=True)
            path.write_text("""/-
Copyright (c) 2014 Jeremy Avigad.
Authors: Jeremy Avigad, Leonardo de Moura
-/
theorem demo : True := trivial
""")
            class Completed:
                stdout=SOURCE_COMMIT+"\n"
            with patch("math_mcts.mathlib_credit_index.subprocess.run",
                       return_value=Completed()):
                report=index_module_authors(db,root)
            self.assertEqual(report["registered_theorems"],2)
            self.assertEqual(report["linked_theorems"],2)
            credit=module_credit(db,"Mathlib.Algebra.Group.Basic")
            self.assertIn("Jeremy Avigad",credit["module_header_authors"])
            self.assertEqual(credit["original_theorem_author"],
                             "not_individually_identified")


if __name__=="__main__":
    unittest.main()
