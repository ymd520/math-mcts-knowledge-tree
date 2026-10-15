"""Evidence boundaries and branch-diversity tests for the 49-field audit.

These tests distinguish source module paths, indexed source rows, editorial
difficulty suggestions, existing curated cards and unverified AI proposals.
A lexical or title match never constitutes a verified mathematical theorem.
"""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from math_mcts.field_audit import audit_fields, choose_audit_queue, load_taxonomy
from math_mcts.knowledge import Concept, KnowledgeTree
from math_mcts.search import CollisionProblem, collide_concepts
from math_mcts.ai_knowledge import validate_pack

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/"examples"/"field_replenishment_v1.json"
SUGGESTIONS=ROOT/"math_mcts"/"data"/"field_level_review_suggestions_v1.json"


def concept(cid,dom,branch,title,level=2,status="",tags=()):
    return Concept(id=cid,domain_cn=dom,domain_en=dom,
                   branch_cn=branch,topic_cn="tests",
                   cn=title,en=title,definition="Toy fixture only.",
                   level=level,level_status=status,tags=list(tags))


class FieldInventoryTests(unittest.TestCase):
    def test_taxonomy_validity_and_exact_research_domains(self):
        rows=load_taxonomy()
        self.assertEqual(len(rows),49)
        self.assertEqual(len({x["id"] for x in rows}),49)
        self.assertEqual(len({x["domain"] for x in rows}),7)
        self.assertTrue(all(x["module_prefixes"] and x["curated_title_terms"]
                            for x in rows))

    def test_no_module_prefix_masquerading_as_theorem_count(self):
        tree=KnowledgeTree([
            concept("C1","代数","同调代数","Homological algebra",4,"",("重要",)),
            concept("C2","代数","同调代数","Homology",5,"ungraded_import",()),
        ])
        ix={"Mathlib.Algebra.Homology":["s"],"Mathlib.Algebra.Homology.Basic":["s"],
            "Mathlib.Algebra.HomologicalFake":["s"]}
        report=audit_fields(tree=tree,module_index=ix,
                            source_manifest={"imported_cards":234576})
        field=next(x for x in report["fields"] if x["id"]=="A06")
        self.assertEqual(field["module_index_paths_matched"],2)
        self.assertEqual(field["catalog_lexical_matches"],2)
        self.assertEqual(field["catalog_important_tagged"],1)
        self.assertEqual(field["catalog_level_counts_not_certified"]["4"],1)
        self.assertEqual(field["catalog_level_counts_not_certified"]["unrated_or_provisional"],1)
        self.assertIsNone(field["indexed_imported_records"])
        self.assertIsNone(field["independent_theorem_proof_count"])
        self.assertFalse(report["claims"]["multilabel_field_totals_can_be_summed_to_unique_count"])

    def test_real_index_row_counts_are_independent_and_nil_is_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"index.sqlite"
            with sqlite3.connect(p) as db:
                db.execute("""CREATE TABLE classified_knowledge (
                 source_module TEXT, source_tier TEXT, registration_status TEXT,
                 importance_status TEXT, difficulty_level INTEGER)""")
                db.executemany("INSERT INTO classified_knowledge VALUES(?,?,?,?,?)",[
                    ("Mathlib.Algebra.Homology.Basic","unreviewed_import",
                     "source_statement_registered","importance_unrated",None),
                    ("Mathlib.Algebra.Homology.Basic","unreviewed_import",
                     "source_statement_registered","importance_unrated",None),
                    ("Mathlib.Algebra.Homology.Exact","curated",
                     "curated_entry","existing_important_tag",3)])
            r=audit_fields(tree=KnowledgeTree([]),
                module_index={"Mathlib.Algebra.Homology.Basic":["f"]},
                indexed_db=p,source_manifest={"imported_cards":3})
            f=next(x for x in r["fields"] if x["id"]=="A06")
            self.assertEqual(f["indexed_imported_records"],2)
            self.assertEqual(f["indexed_curated_records"],1)
            self.assertEqual(f["indexed_source_registered"],2)
            self.assertEqual(f["indexed_imported_grade_unassigned"],2)
            self.assertEqual(f["indexed_imported_importance_unrated"],2)
            self.assertIsNone(f["independent_theorem_proof_count"])

    def test_pack_is_unreviewed_and_classified_by_exact_field(self):
        pack=validate_pack(json.loads(PACK.read_text(encoding="utf-8")))
        self.assertEqual(len(pack["items"]),35)
        self.assertEqual(len({x["local_id"] for x in pack["items"]}),35)
        self.assertTrue(all(x["curation_status"]=="unreviewed_ai_generated" and
                            x["difficulty_level"] is None and
                            not x["proof_verified"] and not x["references_verified"]
                            for x in pack["items"]))
        report=audit_fields(
            tree=KnowledgeTree([]),module_index={},
            source_manifest={"imported_cards":0},ai_candidates=pack["items"])
        self.assertEqual(report["ai_proposals_total_separate"],35)
        self.assertEqual(sum(x["ai_unreviewed_field_proposals"] for x in report["fields"]),35)
        self.assertEqual(report["total_catalog_rows"],0)

    def test_level_suggestions_only_separate_editors_queue(self):
        pack=json.loads(PACK.read_text(encoding="utf-8"))
        suggestions=json.loads(SUGGESTIONS.read_text(encoding="utf-8"))
        self.assertEqual(suggestions["schema"],"math-mcts-level-review-suggestions-v1")
        self.assertEqual(len(suggestions["proposals"]),35)
        self.assertEqual({x["local_id"] for x in pack["items"]},
                         {x["local_id"] for x in suggestions["proposals"]})
        self.assertTrue(all(x["importance"]=="needs_human_assessment" and
                            type(x["suggested_level"]) is int and
                            1<=x["suggested_level"]<=5 and
                            not x["proof_verified"]
                            for x in suggestions["proposals"]))
        self.assertTrue(all("level" not in x and "importance" not in x
                            for x in pack["items"]))

    def test_queue_is_deterministic_and_prioritizes_p0(self):
        r=audit_fields(tree=KnowledgeTree([]),module_index={},
                       source_manifest={"imported_cards":0})
        queue=choose_audit_queue(r,max_fields=12)
        queue2=choose_audit_queue(r,max_fields=12)
        self.assertEqual(queue,queue2)
        self.assertEqual(len(queue),12)
        self.assertTrue(all(x["priority_is_editorial_not_mathematical"] for x in queue))
        with self.assertRaises(ValueError):
            choose_audit_queue(r,max_fields=0)


class CrossBranchMCTSTests(unittest.TestCase):
    def fixture(self):
        return KnowledgeTree([
            concept("A","代数","表示论","representation",level=5,tags=["重要"]),
            concept("B","代数","代数数论","number_theory",level=4,tags=["重要"]),
            concept("C","分析","泛函分析","analysis",level=4,tags=["重要"]),
            concept("D","代数","表示论","samebranch",level=4,tags=["重要"]),
        ])

    def test_default_only_cross_major_domains_preserved(self):
        tree=self.fixture()
        problem=CollisionProblem(tree,"A")
        self.assertEqual(problem.actions(("A",)),["C"])
        result=collide_concepts(tree,seed="A",iterations=100,top_k=5)
        self.assertTrue(result)
        self.assertTrue(all(a.domain_cn!=b.domain_cn for a,b,_,_ in result))

    def test_optin_branch_mode_pairs_same_domain_different_branches(self):
        tree=self.fixture()
        problem=CollisionProblem(tree,"A",diversity_axis="branch")
        opts=problem.actions(("A",))
        self.assertIn("B",opts)
        self.assertIn("C",opts)
        self.assertNotIn("D",opts)
        result=collide_concepts(tree,seed="A",iterations=600,top_k=5,
                                 diversity_axis="branch")
        self.assertTrue(result)
        self.assertTrue(any(a.domain_cn==b.domain_cn
                            and a.branch_cn!=b.branch_cn
                            for a,b,_,_ in result))
        self.assertTrue(all((a.domain_cn,a.branch_cn)!=(b.domain_cn,b.branch_cn)
                            for a,b,_,_ in result))

    def test_bad_diversity_axis_fails_closed(self):
        tree=self.fixture()
        with self.assertRaises(ValueError):
            CollisionProblem(tree,diversity_axis="invented")
        with self.assertRaises(ValueError):
            collide_concepts(tree,seed="A",iterations=20,diversity_axis="none")


if __name__=="__main__":
    unittest.main()
