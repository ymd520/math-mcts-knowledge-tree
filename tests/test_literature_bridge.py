"""No-network provenance and hybrid-corpus regression tests."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.literature_bridge import (
    HybridCorpus, cache_theoremsearch, normalize_theoremsearch, query_theoremsearch,
)
from math_mcts.source_expansion import search as source_search


HIT = {
    "statement_id": "example-statement-1", "name": "Lemma 2.4",
    "kind": "lemma", "body": "Every compact metric space is sequentially compact.",
    "source": "arXiv", "title": "Compactness notes",
    "authors": ["A. Researcher", "B. Mathematician"],
    "url": "https://arxiv.org/abs/2601.00001", "external_id": "2601.00001",
    "score": 0.9
}


class FakeResponse:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, n):
        return self.data[:n]


class Primary:
    def __init__(self):
        self.total = 1
        self.imported = 1
        self.scope_count = 1
        self.loaded_ids = set()
        self.retrieved_ids = set()
        self.explored_ids = set()
        self.search_calls = 0
        self.sample_calls = 0
        self.closed = False
        self.base = {
            "id": "I1", "name": "compactness", "english_name": "compactness",
            "domain": "topology", "module": "Mathlib.Topology",
            "statement": "A compact mathematical result", "source_tier": "unreviewed_import",
            "_tokens": frozenset({"compactness"}),
            "attribution": {"source_project": "mathlib4"},
        }

    def get(self, cid):
        if cid != "I1":
            raise KeyError(cid)
        self.loaded_ids.add(cid)
        return self.base

    def search(self, query, limit):
        self.search_calls += 1
        self.retrieved_ids.add("I1")
        return [self.get("I1")] if limit else []

    def sample(self, rng, limit):
        self.sample_calls += 1
        return []

    def public_card(self, cid):
        return {k: v for k, v in self.get(cid).items() if not k.startswith("_")}

    def close(self):
        self.closed = True


class LiteratureBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "literature.sqlite"
        self.transport_calls = []

    def opener(self, request, timeout):
        self.transport_calls.append((request.full_url, timeout))
        return FakeResponse({"results": [HIT]})

    def test_metadata_and_rights_not_promoted(self):
        rows, report = normalize_theoremsearch({"results": [HIT]})
        self.assertEqual(report["accepted"], 1)
        row = rows[0]
        self.assertEqual(row["authors"], "A. Researcher; B. Mathematician")
        self.assertEqual(row["source_url"], HIT["url"])
        self.assertEqual(row["source_provider"], "TheoremSearch")
        self.assertEqual(row["external_id"], "2601.00001")
        self.assertIn("unverified", row["license"])
        self.assertTrue(row["source_ref"].startswith("api-content-sha256-"))
        self.assertFalse(report["proofs_verified"])
        self.assertFalse(report["source_licenses_verified"])

    def test_remote_client_is_explicit_and_bounded(self):
        rows, report = query_theoremsearch("compact metric space", opener=self.opener, limit=3)
        self.assertEqual(len(rows), 1)
        self.assertIn("/graph/embedding?", self.transport_calls[0][0])
        self.assertIn("n_results=3", self.transport_calls[0][0])
        self.assertEqual(report["accepted"], 1)
        with self.assertRaisesRegex(ValueError, "1..20"):
            query_theoremsearch("compact", limit=21, opener=self.opener)
        with self.assertRaisesRegex(ValueError, "nonempty"):
            query_theoremsearch("   ", opener=self.opener)

    def test_missing_or_untrusted_source_is_quarantined(self):
        no_url = {**HIT, "url": "http://untrusted.example.org/theorem"}
        no_id = {**HIT, "statement_id": ""}
        no_body = {**HIT, "body": "short"}
        rows, info = normalize_theoremsearch({"results": [no_url, no_id, no_body]})
        self.assertEqual(rows, [])
        self.assertEqual(info["accepted"], 0)
        self.assertEqual(sum(info["rejected"].values()), 3)

    def test_repeated_cache_import_idempotent(self):
        one = cache_theoremsearch(self.db, "compactness", opener=self.opener)
        two = cache_theoremsearch(self.db, "compactness", opener=self.opener)
        self.assertEqual(one["imported"], 1)
        self.assertEqual(two["imported"], 0)
        self.assertEqual(two["already_present"], 1)
        result = source_search(self.db, "compact")
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["license_verified"])
        self.assertEqual(result[0]["curation_status"], "unreviewed_external_source")

    def test_hybrid_retrieval_preserves_primary_coverage_and_citation(self):
        cache_theoremsearch(self.db, "compactness", opener=self.opener)
        primary = Primary()
        mixed = HybridCorpus(primary, self.db, quota=2)
        try:
            self.assertEqual(mixed.total, 1)
            self.assertEqual(mixed.imported, 1)
            self.assertEqual(mixed.external_count, 1)
            cards = mixed.search("compact sequential", 4)
            self.assertEqual(cards[0]["id"], "I1")
            external = [x for x in cards if x["id"].startswith("EXT_")]
            self.assertEqual(len(external), 1)
            c = external[0]
            self.assertFalse(c["proof_verified_by_this_search"])
            self.assertEqual(c["attribution"]["authors"], "A. Researcher; B. Mathematician")
            self.assertEqual(c["attribution"]["source_project_url"], HIT["url"])
            self.assertFalse(c["attribution"]["license_verified"])
            self.assertEqual(mixed.get(c["id"])["id"], c["id"])
            self.assertEqual(mixed.external_retrieved_ids, {c["id"]})
            self.assertEqual(mixed.search("compact sequential", 4), cards)
        finally:
            mixed.close()
        self.assertTrue(primary.closed)

    def test_missing_or_corrupt_cache_does_not_silently_fallback(self):
        base = Primary()
        with self.assertRaisesRegex(ValueError, "does not exist"):
            HybridCorpus(base, self.db)
        self.assertFalse(base.closed)
        self.db.write_bytes(b"not a SQLite database")
        with self.assertRaisesRegex(ValueError, "Invalid or incomplete"):
            HybridCorpus(base, self.db)


if __name__ == "__main__":
    unittest.main()
