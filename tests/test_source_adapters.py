"""Adapter contract, legal boundaries and provider-diverse retrieval (fully offline tests)."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.source_adapters import (
    PROJECTS, ZBMATH_PIN, fetch_into_cache, fetch_realmath_rows,
    fetch_s2orc_papers, fetch_zbmath_sample, import_local,
    normalize_mathpile, normalize_realmath, normalize_s2orc,
    normalize_semantic_scholar, normalize_zbmath,
)
from math_mcts.source_expansion import inventory, search
from math_mcts.literature_bridge import HybridCorpus
from math_mcts.indexed_mcts import KnowledgeMCTSProblem


class Response:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n):
        return self.content[:n]


class FakeTransport:
    def __init__(self):
        self.urls = []

    def __call__(self, request, timeout=15):
        self.urls.append(request.full_url)
        u = request.full_url
        if "/splits?" in u:
            payload = {"splits": [{"split": "Math_arXiv", "config": "default"}]}
        elif "/rows?" in u:
            payload = {"rows": [{"row_idx": 21, "row": {
                "link": "http://arxiv.org/abs/2601.00002v1",
                "theorem": "For all finite simple groups, a placeholder statement.", "question": "Group theorem?"}}]}
        elif "/graph/v1/paper/search?" in u:
            payload = {"data": [{
                "paperId": "abc123", "title": "Finite group theory survey",
                "url": "https://www.semanticscholar.org/paper/abc123",
                "authors": [{"name": "Professor One"}],
                "externalIds": {"ArXiv": "2601.00003", "DOI": "10.1000/xyz"},
                "fieldsOfStudy": ["Mathematics"], "year": 2026}]}
        elif "zbmath-open-kg" in u:
            payload = None
            b = (json.dumps({"zbl_id": ["ZBL-123"], "document_title": ["Finite group review"],
                 "author": ["Expert Author"], "classification": ["20D05"],
                 "keyword": ["finite groups"], "review_text": ["A review of finite group results."],
                 "doi": ["10.1000/abc"]}) + "\n").encode()
            return Response(b)
        else:
            raise AssertionError("Unexpected API " + u)
        return Response(json.dumps(payload).encode())


class StubPrimary:
    domain = None

    def __init__(self):
        self.cards = {
            "P1": {"id": "P1", "domain": "algebra", "name": "finite group review",
                   "english_name": "finite group review", "module": "",
                   "_tokens": frozenset({"finite", "group", "review"}),
                   "source_tier": "unreviewed_import"}
        }
        self.total = 1
        self.imported = 1
        self.close_called = False

    def get(self, cid):
        return self.cards[cid]

    def search(self, query, limit):
        return list(self.cards.values())[:limit]

    def sample(self, rng, limit):
        return []

    def close(self):
        self.close_called = True


class SourceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.db = self.root / "external.sqlite"

    def jsonl(self, *items):
        p = self.root / "data.jsonl"
        with p.open("w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item) + "\n")
        return p

    def test_project_registry_has_six_distinct_attributed_projects(self):
        self.assertEqual(set(PROJECTS),
            {"theoremsearch", "zbmath", "s2orc", "realmath", "mathpile", "mathlib4"})
        self.assertTrue(all(x["url"].startswith("https://") for x in PROJECTS.values()))
        self.assertTrue(PROJECTS["mathpile"]["mode"].startswith("user-authorized"))

    def test_source_metadata_normalization_and_no_proof_forgery(self):
        zb = normalize_zbmath({
            "zbl_id": ["1234.56789"], "document_title": ["Geometry paper"],
            "author": ["Original Mathematician"], "review_text": ["Reviewed mathematics discussion"],
            "classification": ["53A01"], "keyword": ["geometry"]})
        self.assertEqual(zb["source"], "zbmath")
        self.assertEqual(zb["kind"], "review")
        self.assertIn("Original Mathematician", zb["authors"])
        self.assertIn("https://zbmath.org/", zb["source_url"])
        paper = normalize_semantic_scholar({
            "paperId": "xx", "title": "General topology",
            "url": "https://papers.example.org/xx", "authors": [{"name": "Author"}]})
        self.assertEqual(paper["kind"], "paper")
        self.assertNotIn("theorem", paper["kind"])
        self.assertIn("metadata only", paper["source_precision"])
        rm = normalize_realmath({
            "link": "http://arxiv.org/abs/2601.00001v1",
            "theorem": "Let G be a finite group and satisfy all assumptions.",
            "question": "Theorem question?"}, 42)
        self.assertEqual(rm["kind"], "theorem")
        self.assertTrue(rm["source_url"].startswith("https://arxiv.org/"))
        self.assertIn("unknown", rm["source_precision"])
        mp = normalize_mathpile({"text": "Long mathematics corpus text about homology.",
                                 "SubSet": "Textbooks", "meta": {"idx": 22}}, 5)
        self.assertEqual(mp["kind"], "excerpt")
        self.assertIn("original text source unknown", mp["source_precision"])
        self.assertIn("non-commercial", mp["reuse_policy"])
        self.assertNotEqual(paper["source_ref"], zb["source_ref"])

    def test_s2orc_text_is_opt_in_and_not_proof(self):
        r = {"corpusid": 123, "title": "Groups and representations",
             "externalids": {"ArXiv": "2601.00004"}, "content": {
                 "text": "Detailed mathematical content with theorem and proof."}}
        a = normalize_s2orc(r)
        b = normalize_s2orc(r, include_text=True)
        self.assertEqual(a["kind"], "paper")
        self.assertEqual(b["kind"], "excerpt")
        self.assertNotIn("Detailed mathematical", a["statement"])
        self.assertIn("Detailed mathematical", b["statement"])

    def test_local_license_gate_and_bounded_import(self):
        r = {"text": "A useful mathematical lemma from a corpus.",
             "SubSet": "arXiv", "meta": {"idx": 13}}
        file = self.jsonl(r)
        with self.assertRaises(PermissionError):
            import_local(self.db, "mathpile", file)
        report = import_local(self.db, "mathpile", file, ack_license=True)
        self.assertEqual(report["inserted"], 1)
        self.assertFalse(report["full_dataset_indexed"])
        rec = search(self.db, "lemma")
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]["kind"], "excerpt")
        self.assertFalse(rec[0]["proof_verified_this_run"])
        self.assertFalse(rec[0]["license_verified"])
        s2 = self.jsonl({"corpusid": 100, "title": "Group analysis note",
                         "content": {"text": "Full text of an original paper."}})
        with self.assertRaises(PermissionError):
            import_local(self.db, "s2orc", s2, include_text=True)
        result = import_local(self.db, "s2orc", s2, include_text=True, ack_license=True)
        self.assertEqual(result["inserted"], 1)

    def test_live_adapters_use_real_documented_endpoints_and_bounded_cache(self):
        fake = FakeTransport()
        result = fetch_into_cache(self.db, "s2orc", query="finite group", limit=4, opener=fake)
        self.assertEqual(result["inserted"], 1)
        found = search(self.db, "finite group")
        self.assertEqual(found[0]["kind"], "paper")
        self.assertEqual(found[0]["doi"], "10.1000/xyz")
        self.assertTrue(any("fields=" in u for u in fake.urls))
        result = fetch_into_cache(self.db, "realmath", limit=4, opener=fake)
        self.assertEqual(result["inserted"], 1)
        self.assertTrue(any("/splits?" in u for u in fake.urls))
        self.assertTrue(any("/rows?" in u for u in fake.urls))
        result = fetch_into_cache(self.db, "zbmath", limit=4, opener=fake)
        self.assertEqual(result["inserted"], 1)
        self.assertTrue(any(ZBMATH_PIN in u for u in fake.urls))
        self.assertEqual(inventory(self.db)["external_candidates"], 3)

    def test_diverse_source_search_preserves_primary_and_real_provenance(self):
        source_data = [
            {"text": "finite group useful lemma in geometry", "SubSet": "ProofWiki",
             "meta": {"idx": 9}},
            {"text": "finite group useful lemma in topology", "SubSet": "arXiv",
             "meta": {"idx": 10}},
            {"text": "finite group useful lemma in topology", "SubSet": "Textbooks",
             "meta": {"idx": 11}},
        ]
        import_local(self.db, "mathpile", self.jsonl(*source_data), ack_license=True)
        fake = FakeTransport()
        fetch_into_cache(self.db, "zbmath", limit=5, opener=fake)
        fetch_into_cache(self.db, "s2orc", query="finite group", limit=5, opener=fake)
        primary = StubPrimary()
        mixed = HybridCorpus(primary, self.db, quota=3)
        try:
            hits = mixed.search("finite group", 6)
            self.assertTrue(any(x["id"] == "P1" for x in hits))
            ext = [h for h in hits if h["id"].startswith("EXT_")]
            self.assertGreaterEqual(len({h["attribution"]["source_project"] for h in ext}), 2)
            self.assertTrue(all(h["source_tier"] == "unreviewed_external_source" for h in ext))
            self.assertTrue(all(h["attribution"]["license_verified"] is False for h in ext))
            self.assertEqual(mixed.external_count, 5)
            self.assertEqual(mixed.total, 1)
            # Identical query should reuse bounded shortlist cache.
            before = len(mixed._qcache)
            mixed.search("finite group", 6)
            self.assertEqual(len(mixed._qcache), before)
        finally:
            mixed.close()
        self.assertTrue(primary.close_called)


if __name__ == "__main__":
    unittest.main()
