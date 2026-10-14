"""Fast index, typed bridge and provenance fingerprint regression suite."""
import copy
import gzip
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.fast_index import build_index, fast_search, index_stats, terms_for
from math_mcts.knowledge import KnowledgeTree
from math_mcts.reasoning import Atom, Rule, RuleBook, derive, verify_certificate
from math_mcts.semantic import catalog_statement_sha256, load_catalog_reasoning_problem
from math_mcts.semantic_links import compatible_atoms, find_composable_rules
from math_mcts.search import plan_learning_path
from test_semantic_audit import example_problem, example_tree


class ScaleTests(unittest.TestCase):
    def test_small_provenance_verified_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for i, domain in enumerate(("Algebra", "Analysis", "Analysis", "Algebra")):
                rows.append({
                    "id": f"IMP{i}", "en": f"Statement_{i}_smul",
                    "cn": f"数学声明{i}", "definition": "样本形式定理",
                    "formal": f"theorem Statement_{i}_smul : True",
                    "module": f"Mathlib.{domain}.Test", "domain_en": domain,
                    "domain_cn": domain, "level": 5, "tags": ["待审"],
                    "verification_status": "pending",
                    "source_url": f"https://example.org/{i}",
                    "original_metadata": {"陈述SHA256": hashlib.sha256(
                        f"Statement {i}".encode()).hexdigest()}})
            archive = gzip.compress(json.dumps({"concepts": rows}).encode())
            (root / "test.json.gz").write_bytes(archive)
            (root / "manifest.json").write_text(json.dumps({
                "files": [{"shard": "test.json.gz", "card_count": 4,
                           "shard_sha256": hashlib.sha256(archive).hexdigest()}]}))
            db = root / "index.sqlite"
            report = build_index(db, candidate_limit=3, include_curated=False,
                                 imported_root=root)
            self.assertEqual(report["unreviewed_candidates"], 3)
            found = fast_search(db, "smul", top_k=3)
            self.assertEqual(len(found), 3)
            self.assertTrue(all(row["index_tier"] == "unreviewed_import" and
                                row["indexed_level"] is None for row in found))
            self.assertEqual(index_stats(db)["metadata"]["unreviewed_candidate_count"], "3")

    def test_duplicate_source_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{"id": f"IMP{i}", "en": f"t{i}", "definition": "t",
                     "formal": f"theorem t{i}", "domain_en": "Analysis",
                     "original_metadata": {"陈述SHA256": "same"}} for i in range(2)]
            blob = gzip.compress(json.dumps({"concepts": rows}).encode())
            (root / "s.json.gz").write_bytes(blob)
            (root / "manifest.json").write_text(json.dumps({"files": [{
                "shard": "s.json.gz", "shard_sha256": hashlib.sha256(blob).hexdigest(),
                "card_count": 2}]}))
            with self.assertRaisesRegex(ValueError, "Duplicate imported"):
                build_index(root / "index.db", include_curated=False, imported_root=root)

    def test_cjk_terms_and_query_injection(self):
        self.assertIn("矩阵", terms_for("矩阵计算"))
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "curated.db"
            build_index(db, include_curated=True, include_imported=False)
            self.assertIsInstance(fast_search(db, '" OR ('' ', top_k=5), list)
            self.assertTrue(fast_search(db, "矩阵", top_k=5, tier="curated"))

    def test_exact_identity_in_certificate_fingerprint(self):
        tree = example_tree()
        other = copy.deepcopy(tree.get("T1"))
        other.id = "T2"
        tree = KnowledgeTree([tree.get("T1"), other])
        payload = example_problem(tree)
        book1, ass, goal = load_catalog_reasoning_problem(payload, tree)
        result = derive(book1, ass, goal, iterations=10)
        self.assertIsNotNone(result.certificate)
        alternate = copy.deepcopy(payload)
        alternate["rules"][0]["concept_id"] = "T2"
        alternate["rules"][0]["concept_sha256"] = catalog_statement_sha256(tree.get("T2"))
        book2, _, _ = load_catalog_reasoning_problem(alternate, tree)
        self.assertNotEqual(book1.fingerprint(), book2.fingerprint())
        self.assertFalse(verify_certificate(book2, result.certificate, ass, goal))
        altered = copy.deepcopy(payload)
        altered["rules"][0]["mapping_review"] += " extra"
        book3, _, _ = load_catalog_reasoning_problem(altered, tree)
        self.assertNotEqual(book1.fingerprint(), book3.fingerprint())

    def test_known_target_is_terminal(self):
        tree = KnowledgeTree.load()
        target = tree.find("傅里叶变换")
        unrelated = next(x for x in tree.concepts if x.id != target.id)
        path = plan_learning_path(tree, target.id,
                                  known=[target.id, unrelated.id])
        self.assertEqual([x.id for x in path], [target.id])


class CompositionTests(unittest.TestCase):
    def test_unification_constant_conflicts_and_repeated_variables(self):
        self.assertFalse(compatible_atoms(Atom("p", ("?x", "?x")),
                                          Atom("p", ("a", "b"))))
        self.assertTrue(compatible_atoms(Atom("p", ("?x", "?x")),
                                         Atom("p", ("?y", "?y"))))
        self.assertFalse(compatible_atoms(Atom("p", ("a",)),
                                          Atom("different", ("a",))))

    def test_compositions_are_typed_and_not_proof_claims(self):
        rules = [
            Rule("source", (Atom("q", ("?x",)),), Atom("p", ("?x", "?x")),
                 (("?x", "S"),), source="synthetic", status="reviewed"),
            Rule("blocked", (Atom("p", ("a", "b")),), Atom("out", ()),
                 source="synthetic", status="reviewed"),
            Rule("allowed", (Atom("p", ("?y", "?y")),), Atom("out", ()),
                 (("?y", "S"),), source="synthetic", status="reviewed"),
        ]
        book = RuleBook({"q": ("S",), "p": ("S", "S"), "out": ()},
                        {"a": "S", "b": "S"}, rules)
        pairs = find_composable_rules(book)
        self.assertTrue(any(p["producer"] == "source" and p["consumer"] == "allowed"
                            for p in pairs))
        self.assertFalse(any(p["producer"] == "source" and p["consumer"] == "blocked"
                             for p in pairs))
        self.assertTrue(all("not_a_proof" in x["status"] for x in pairs))


if __name__ == "__main__":
    unittest.main()
