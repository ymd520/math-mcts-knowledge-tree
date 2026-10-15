"""Adversarial tests: model-authored math stays a queryable UNREVIEWED candidate.

Prove the bridge actually feeds the existing MCTS collision engine without
granting candidate status, proof truth, importance or trusted Horn rules.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.ai_knowledge import (
    SCHEMA, candidate_tree, collide_for_research, ingest_file, ingest_pack,
    inventory, lookup, query_for_research, to_candidate_concept, validate_pack
)
from math_mcts.knowledge import KnowledgeTree, Concept
from math_mcts.reasoning import Atom, Rule, RuleBook

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "examples" / "ai_knowledge_seed_v1.json"


def example():
    return {
        "schema": SCHEMA,
        "generator": {
            "system": "ChatGPT", "model": "GPT-6",
            "run_id": "model-run-001", "generated_at": "2026-10-15"
        },
        "items": [
            {"local_id":"A1","kind":"theorem","domain":"代数",
             "branch":"群论","topic":"有限群","title":"Cosets partition a group",
             "statement":"Every left coset of H in a finite group G has size |H|.",
             "assumptions":"G finite group and H subgroup of G.",
             "conclusion":"Each left coset has cardinality |H|.",
             "proof_idea":"Use multiplication by g as a bijection.",
             "keywords":["coset","Lagrange"],"references":[]},
            {"local_id":"B1","kind":"method","domain":"概率与统计",
             "branch":"概率论","topic":"计数","title":"Bijection counting",
             "statement":"Find a bijection between two finite sets to compare their sizes.",
             "assumptions":"Both sets are finite and an explicit bijection is given.",
             "conclusion":"The two sets have equal size.",
             "keywords":["bijection","Lagrange"],"references":[]},
        ],
    }


class AIPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "ai.sqlite"

    def test_round_trip_and_candidate_only_state(self):
        first = ingest_pack(self.db, example())
        self.assertEqual(first["new_candidates"], 2)
        self.assertEqual(first["new_curated"], 0)
        self.assertEqual(first["verified_proofs"], 0)
        again = ingest_pack(self.db, example())
        self.assertEqual(again["new_candidates"], 0)
        self.assertEqual(again["new_observations"], 0)
        self.assertEqual(again["previously_seen_content"], 2)
        self.assertEqual(inventory(self.db)["unreviewed_ai_candidates"], 2)
        self.assertEqual(inventory(self.db)["generator_observations"], 2)
        matches = lookup(self.db, "coset", limit=20)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["curation_status"], "unreviewed_ai_generated")
        self.assertIsNone(matches[0]["difficulty_level"])
        self.assertFalse(matches[0]["proof_verified"])
        self.assertFalse(matches[0]["references_verified"])

    def test_distinct_runs_append_attribution_not_duplicate_contents(self):
        pack = example()
        ingest_pack(self.db, pack)
        second = copy.deepcopy(pack)
        second["generator"]["run_id"] = "model-run-002"
        count = ingest_pack(self.db, second)
        self.assertEqual((count["new_candidates"], count["new_observations"]), (0, 2))
        self.assertEqual(inventory(self.db)["generator_observations"], 4)
        matches = lookup(self.db, "coset")
        self.assertEqual(matches[0]["observation_count"], 2)

    def test_conflicting_source_snapshot_rolls_back_entire_batch(self):
        pack = example()
        ingest_pack(self.db, pack)
        forged = copy.deepcopy(pack)
        forged["items"][0]["statement"] += " CHANGED"
        with self.assertRaisesRegex(ValueError, "changed"):
            ingest_pack(self.db, forged)
        self.assertEqual(inventory(self.db)["unreviewed_ai_candidates"], 2)
        self.assertEqual(inventory(self.db)["generator_observations"], 2)

    def test_conflicting_source_metadata_rolls_back(self):
        pack = example()
        ingest_pack(self.db, pack)
        forged = copy.deepcopy(pack)
        forged["generator"]["model"] = "another-model"
        with self.assertRaisesRegex(ValueError, "changed"):
            ingest_pack(self.db, forged)
        self.assertEqual(inventory(self.db)["generator_observations"], 2)

    def test_lexical_dedup_not_semantic_equivalence(self):
        pack = example()
        pack["items"][1] = copy.deepcopy(pack["items"][0])
        pack["items"][1]["local_id"] = "B1"
        pack["items"][1]["statement"] = "Every   left coset of H in a finite group G has size |H|."
        result = ingest_pack(self.db, pack)
        self.assertEqual(result["new_candidates"], 1)
        self.assertEqual(result["new_observations"], 2)
        changed = copy.deepcopy(pack)
        changed["generator"]["run_id"] = "new-run"
        changed["items"][1]["statement"] = "Left cosets of H and H itself have the same size."
        result = ingest_pack(self.db, changed)
        self.assertEqual(result["new_candidates"], 1)
        self.assertEqual(inventory(self.db)["unreviewed_ai_candidates"], 2)

    def test_unknown_status_or_importance_fields_rejected_atomically(self):
        for field,value in [("proof_verified",True),("level",1),
                            ("tags",["核心"]),("status","reviewed"),
                            ("curation_status","verified"),("importance_status","core")]:
            with self.subTest(field=field):
                pack = example()
                pack["items"][1][field] = value
                with self.assertRaises(ValueError):
                    ingest_pack(self.db, pack)
                self.assertEqual(inventory(self.db)["unreviewed_ai_candidates"], 0)

    def test_missing_assumptions_or_source_claim_unsafe(self):
        pack = example()
        del pack["items"][0]["assumptions"]
        with self.assertRaisesRegex(ValueError, "missing required"):
            ingest_pack(self.db, pack)
        pack = example()
        pack["items"][0]["references"] = [{"title":"Paper","locator":"page 1",
                                           "url":"file:///etc/passwd"}]
        with self.assertRaises(ValueError):
            ingest_pack(self.db, pack)
        self.assertEqual(inventory(self.db)["unreviewed_ai_candidates"], 0)

    def test_local_id_collision_invalid(self):
        pack = example()
        pack["items"][1]["local_id"] = pack["items"][0]["local_id"]
        with self.assertRaisesRegex(ValueError, "duplicate local_id"):
            ingest_pack(self.db, pack)

    def test_model_and_run_are_claimed_not_authenticated(self):
        pack = example()
        pack["generator"]["system"] = "UnverifiedCallerAssertion"
        pack["generator"]["model"] = "FictionalModel"
        ingest_pack(self.db, pack)
        self.assertEqual(lookup(self.db, "coset")[0]["curation_status"],
                         "unreviewed_ai_generated")

    def test_seed_pack_cross_domain_loaded_and_mcts_collision(self):
        outcome = ingest_file(self.db, SEED)
        self.assertEqual(outcome["new_candidates"], 18)
        index = inventory(self.db)
        self.assertEqual(index["unreviewed_ai_candidates"], 18)
        tree = candidate_tree(self.db, limit=50)
        self.assertEqual(len(tree.concepts), 18)
        self.assertTrue(all(c.verification_status == "not_independently_verified"
                            for c in tree.concepts))
        self.assertTrue(all(c.level_status == "ungraded_ai_candidate"
                            for c in tree.concepts))
        self.assertTrue(all("核心" not in c.tags and not c.prereq
                            for c in tree.concepts))
        pairs = collide_for_research(self.db, limit=30, iterations=1000)
        self.assertGreater(len(pairs), 0)
        self.assertTrue(all(p["conjecture_only"] and not p["proof_verified"]
                            and not p["reviewed_rule_created"]
                            for p in pairs))
        self.assertTrue(all(tree.get(p["a"]).domain_cn != tree.get(p["b"]).domain_cn
                            for p in pairs))

    def test_retrieval_routes_to_existing_exact_ranker_not_fake_mcts(self):
        ingest_pack(self.db, example())
        rows = query_for_research(self.db, "coset", top_k=3)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["curation_status"], "unreviewed_ai_generated")
        self.assertFalse(rows[0]["verified"])

    def test_overlay_never_modifies_curated_tree(self):
        ingest_pack(self.db, example())
        curated = Concept(
            id="CUR01", domain_cn="拓扑", domain_en="Topology",
            branch_cn="拓扑学", topic_cn="基础", cn="compactness", en="compactness",
            definition="A topological property used in mathematics.", level=2,
            tags=["核心"])
        base = KnowledgeTree([curated])
        overlay = candidate_tree(self.db, limit=100, base_tree=base)
        self.assertEqual(len(base.concepts), 1)
        self.assertEqual(len(overlay.concepts), 3)
        self.assertEqual(base.get("CUR01").tags, ["核心"])
        for c in overlay.concepts:
            if c.id.startswith("AI_"):
                self.assertNotIn("核心", c.tags)
                self.assertEqual(c.curation_status, "unreviewed_ai_generated")

    def test_candidate_cannot_be_used_as_reviewed_horn_rule(self):
        ingest_pack(self.db, example())
        candidate = lookup(self.db, "coset")[0]
        # This source is NOT magically a reviewed Horn rule; RuleBook demands
        # declared, typed predicates and explicit caller-reviewed provenance.
        rule = Rule("auto", (Atom("P",("a",)),), Atom("Q",("a",)),
                    status=candidate["curation_status"], source="AI")
        with self.assertRaisesRegex(ValueError, "Unknown rule status"):
            RuleBook({"P":("S",),"Q":("S",)},{"a":"S"},[rule])

    def test_malformed_budget_and_query_sql_safe(self):
        ingest_pack(self.db, example())
        with self.assertRaises(ValueError):
            lookup(self.db,"coset",limit=0)
        self.assertIsInstance(lookup(self.db,'\" OR ("" ',limit=10),list)
        with self.assertRaises(ValueError):
            candidate_tree(self.db,limit=0)


if __name__ == "__main__":
    unittest.main()
