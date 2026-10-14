"""Adversarial audit and explicit card-to-rule mapping tests."""
import copy
import unittest

from math_mcts.audit import audit_catalog
from math_mcts.knowledge import Concept, KnowledgeTree
from math_mcts.semantic import catalog_statement_sha256, load_catalog_reasoning_problem
from math_mcts.reasoning import Atom, derive, verify_certificate


def example_tree():
    c = Concept(id="T1", domain_cn="数学基础", domain_en="Foundations",
                branch_cn="逻辑", topic_cn="蕴含", cn="合成命题", en="Synthetic",
                definition="Synthetic example, not a mathematical theorem",
                assumptions="p", conclusion="q", formulas=["p => q"],
                source_url="https://example.org/fixture",
                verification_status="editorial_statement_review_not_formal")
    return KnowledgeTree([c])


def example_problem(tree):
    return {
        "signatures": {"p": [], "q": []},
        "objects": {},
        "assumptions": [{"predicate": "p", "args": []}],
        "goal": {"predicate": "q", "args": []},
        "rules": [{
            "id": "r1", "concept_id": "T1",
            "concept_sha256": catalog_statement_sha256(tree.get("T1")),
            "mapping_review": "Manually checked for this synthetic fixture",
            "source": "synthetic typed implication",
            "status": "reviewed",
            "premises": [{"predicate": "p", "args": []}],
            "conclusion": {"predicate": "q", "args": []},
            "variables": {},
        }],
    }


class SemanticTests(unittest.TestCase):
    def test_reviewed_mapping_produces_replayable_certificate(self):
        tree = example_tree()
        book, assumptions, goal = load_catalog_reasoning_problem(example_problem(tree), tree)
        result = derive(book, assumptions, goal, iterations=10)
        self.assertIsNotNone(result.certificate)
        self.assertTrue(verify_certificate(book, result.certificate, assumptions, goal))

    def test_changed_statement_invalidates_mapping(self):
        tree = example_tree()
        data = example_problem(tree)
        tree.get("T1").definition = "The underlying mathematical statement was edited"
        with self.assertRaisesRegex(ValueError, "snapshot"):
            load_catalog_reasoning_problem(data, tree)

    def test_missing_explicit_review_is_rejected(self):
        tree = example_tree()
        data = example_problem(tree)
        data["rules"][0]["mapping_review"] = ""
        with self.assertRaisesRegex(ValueError, "review"):
            load_catalog_reasoning_problem(data, tree)

    def test_candidate_mappings_do_not_activate_inference(self):
        tree = example_tree()
        data = example_problem(tree)
        data["rules"][0]["status"] = "candidate"
        data["rules"][0]["mapping_review"] = ""
        book, assumptions, goal = load_catalog_reasoning_problem(data, tree)
        self.assertIsNone(derive(book, assumptions, goal, iterations=10).certificate)

    def test_unknown_catalog_reference_rejected(self):
        tree = example_tree()
        data = example_problem(tree)
        data["rules"][0]["concept_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "Unknown catalog concept"):
            load_catalog_reasoning_problem(data, tree)

    def test_full_audit_counts_errors_without_confusing_unverified(self):
        tree = example_tree()
        tree.get("T1").prereq = ["missing"]
        report = audit_catalog(tree)
        self.assertEqual(report["scanned"], 1)
        self.assertEqual(report["counts"]["dangling_prerequisite"], 1)
        self.assertEqual(report["fatal_count"], 1)
        self.assertEqual(report["metadata"]["statuses"]["editorial_statement_review_not_formal"], 1)

    def test_exact_duplicate_is_flagged_as_candidate_only(self):
        tree = example_tree()
        c = copy.deepcopy(tree.get("T1"))
        c.id = "T2"
        c.cn = "另一个名字"
        tree = KnowledgeTree([tree.get("T1"), c])
        report = audit_catalog(tree)
        self.assertEqual(report["counts"]["identical_statement_candidates"], 1)
        self.assertEqual(report["fatal_count"], 0)


if __name__ == "__main__":
    unittest.main()
