"""Evidence-first import and research-method regression / adversarial tests."""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.method_library import all_operators, recommend
from math_mcts.source_expansion import (
    import_jsonl, inventory, mathlib_review_snapshot, search,
)


def source(locator="theorem_1", statement="For all n, n + 0 = n.",
           source_ref="pinned-commit-abc1234"):
    return {"source": "AFP", "source_ref": source_ref,
            "source_url": "https://www.isa-afp.org/",
            "license": "BSD-3-Clause", "locator": locator,
            "name": "addition_identity", "kind": "theorem",
            "statement": statement, "proof_verified_this_run": True,
            "difficulty_level": 1, "importance_status": "core",
            "curation_status": "verified"}


class ExternalImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "external.sqlite"

    def write(self, *rows, zipped=False):
        p = self.root / ("input.jsonl.gz" if zipped else "input.jsonl")
        opener = gzip.open if zipped else open
        with opener(p, "wt", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        return p

    def test_import_search_and_nonpromotion(self):
        report = import_jsonl(self.db, self.write(source()), max_records=10)
        self.assertEqual(report["inserted"], 1)
        self.assertEqual(report["verified_proofs_this_run"], 0)
        found = search(self.db, "addition", limit=10)
        self.assertEqual(len(found), 1)
        row = found[0]
        self.assertFalse(row["proof_verified_this_run"])
        self.assertFalse(row["license_verified"])
        self.assertIsNone(row["difficulty_level"])
        self.assertEqual(row["importance_status"], "unrated")
        self.assertEqual(row["curation_status"], "unreviewed_external_source")
        self.assertEqual(inventory(self.db)["external_candidates"], 1)

    def test_gzip_idempotency(self):
        path = self.write(source(), zipped=True)
        import_jsonl(self.db, path)
        again = import_jsonl(self.db, path)
        self.assertEqual((again["inserted"], again["already_present_identical"]), (0, 1))
        self.assertEqual(inventory(self.db)["external_candidates"], 1)

    def test_duplicate_lexical_text_not_mathematical_equivalence(self):
        import_jsonl(self.db, self.write(source("a"), source("b")))
        rows = search(self.db, "addition")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(x["same_normalized_text_count"] == 2 for x in rows))
        self.assertTrue(all(x["same_text_means_equivalent"] is False for x in rows))
        self.assertEqual(inventory(self.db)["lexical_duplicate_groups"], 1)

    def test_modified_same_version_rolls_back_whole_batch(self):
        import_jsonl(self.db, self.write(source("a")))
        with self.assertRaisesRegex(ValueError, "changed"):
            import_jsonl(self.db, self.write(source("b"), source("a", "Different mathematical statement")))
        self.assertEqual(inventory(self.db)["external_candidates"], 1)

    def test_bad_row_rolls_back(self):
        bad = source("b")
        bad["source_url"] = "file:///etc/passwd"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            import_jsonl(self.db, self.write(source("a"), bad))
        self.assertEqual(inventory(self.db)["external_candidates"], 0)

    def test_ref_change_not_silent_overwrite(self):
        import_jsonl(self.db, self.write(source("a", "A mathematical statement", "commit-a"),
                                              source("a", "A revised statement", "commit-b")))
        self.assertEqual(inventory(self.db)["external_candidates"], 2)

    def test_empty_or_malformed_input_rejected(self):
        bad = source()
        bad.pop("license")
        with self.assertRaisesRegex(ValueError, "license"):
            import_jsonl(self.db, self.write(bad))
        with self.assertRaises(ValueError):
            import_jsonl(self.db, self.write(source()), max_records=0)

    def test_query_injection_safe(self):
        import_jsonl(self.db, self.write(source()))
        self.assertIsInstance(search(self.db, '\" OR ("" ', limit=10), list)

    def test_existing_math_index_snapshot_counts(self):
        p = self.root / "math_index.sqlite"
        with sqlite3.connect(p) as db:
            db.execute("CREATE TABLE documents (id TEXT, tier TEXT)")
            db.executemany("INSERT INTO documents VALUES(?,?)",
                           [("a", "curated"), ("b", "unreviewed_import")])
            db.execute("CREATE TABLE source_registry (id TEXT)")
            db.execute("INSERT INTO source_registry VALUES('b')")
        snapshot = mathlib_review_snapshot(p)
        self.assertEqual(snapshot["indexed_curated"], 1)
        self.assertEqual(snapshot["indexed_unreviewed_import"], 1)
        self.assertEqual(snapshot["source_registered"], 1)


class OperatorTests(unittest.TestCase):
    def test_methods_have_checkable_obligations(self):
        ops = all_operators()
        self.assertGreaterEqual(len(ops), 30)
        self.assertEqual(len(set(x.key for x in ops)), len(ops))
        for item in ops:
            self.assertTrue(item.requires and item.action and item.failure_test)
            self.assertTrue(item.proof_obligation)
            self.assertTrue(item.category and item.triggers)

    def test_noncommutative_convolution_finds_targeted_tools(self):
        hits = recommend("noncommutative group Fourier convolution upper bound",
                         limit=30)
        keys = {r["key"] for r in hits}
        self.assertIn("fourier_switch", keys)
        self.assertIn("abelian_nonabelian", keys)
        self.assertTrue(all(r["application_status"] ==
                            "proposal_requires_math_verification" for r in hits))

    def test_chinese_and_no_spurious_theorems(self):
        hits = recommend("研究傅里叶卷积的反例", limit=30)
        self.assertIn("fourier_switch", {r["key"] for r in hits})
        self.assertTrue(all(r["discovery_is_new_theorem"] is False for r in hits))
        self.assertEqual(recommend("xyzabsenttrigger"), [])


if __name__ == "__main__":
    unittest.main()
