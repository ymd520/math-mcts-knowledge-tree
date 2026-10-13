import hashlib
import json
import sys
import tempfile
import gzip
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from math_mcts import KnowledgeTree, search_concepts, collide_concepts, DiscoveryQueue
from math_mcts.catalog import assemble, PACK_DIR, name_key


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = KnowledgeTree.load(include_supplements=False)
        cls.tree = KnowledgeTree.load()
        cls.report = json.loads((PACK_DIR / "build_report.json").read_text())

    def test_inventory_and_important_growth(self):
        self.assertEqual(len(self.tree.concepts), len(self.base.concepts) + self.report["added"])
        self.assertEqual(self.tree.check_integrity(), [])
        a, b = self.base.inventory(), self.tree.inventory()
        self.assertGreaterEqual(b["important_levels"][1], a["important_levels"][1])
        self.assertGreaterEqual(b["important_levels"][1], 700)
        for level in range(2, 5):
            self.assertGreater(b["important_levels"][level], a["important_levels"][level])
        self.assertEqual(self.tree.meta["version"], "1.11.0")

    def test_level_and_importance_are_separate(self):
        view = self.tree.select(levels=[1, 2], important_only=True)
        self.assertTrue(view.concepts)
        self.assertTrue(all(c.level in {1, 2} and {"重要", "核心"} & set(c.tags) for c in view.concepts))
        self.assertTrue(view.meta["search_view"])
        with self.assertRaises(ValueError):
            self.tree.select(levels=[0])

    def test_domain_filter_and_collisions(self):
        view = self.tree.select(levels=[1], important_only=True, domains=["代数"])
        self.assertTrue(all(c.domain_cn == "代数" for c in view.concepts))
        self.assertTrue(all(r["a"] in view.by_id and r["b"] in view.by_id for r in view.collisions))

    def test_sources_conditions_and_status(self):
        for row in self.report["authored"]:
            c = self.tree.get(row["id"])
            self.assertTrue(c.assumptions and c.conclusion and c.formulas)
            self.assertTrue(c.source_url.startswith("https://"))
            self.assertTrue(c.source_locator and c.importance_reason)
            self.assertEqual(c.verification_status, "editorial_statement_review_not_formal")
            digest = hashlib.sha256((c.assumptions+"\n"+c.conclusion+"\n"+c.formulas[0]).encode()).hexdigest()
            self.assertEqual(c.statement_sha256, digest)

    def test_no_new_duplicate_chinese_names(self):
        before = self.base.inventory()["duplicate_name_groups"]
        self.assertEqual(self.tree.inventory()["duplicate_name_groups"], before)

    def test_alias_and_ambiguous_lookup(self):
        c = self.tree.find("加法交换律")
        self.assertEqual(self.tree.find("Addition commutativity").id, c.id)
        names = Counter(name_key(c.cn) for c in self.base.concepts)
        duplicated = next(k for k,n in names.items() if n>1)
        self.assertGreater(len(self.tree.find_all(duplicated)), 1)

    def test_difficulty_corrections(self):
        self.assertEqual(self.tree.find("可测空间").level, 3)
        self.assertEqual(self.tree.find("测度空间").level, 3)
        self.assertEqual(self.tree.find("拓扑和").level, 4)

    def test_priorities_do_not_claim_verified(self):
        cid = self.report["structural_priority_ids"][0]
        self.assertIn("依赖结构重要性", self.tree.get(cid).importance_reason)
        if cid not in {r["id"] for r in self.report["authored"]}:
            self.assertEqual(self.tree.get(cid).verification_status, self.base.get(cid).verification_status)

    def test_supplement_integrates_search_and_discovery(self):
        view = self.tree.select(levels=[1], important_only=True)
        matches = search_concepts(view, "分数除法", iterations=300, top_k=3)
        self.assertIn("分数除法", [c.cn for c,_,_ in matches])
        queue = DiscoveryQueue();queue.ingest_concepts(KnowledgeTree([self.tree.find("概率一不等于处处成立")]))
        self.assertEqual(queue.proposals[0]["status"], "unverified")

    def test_hash_tamper_and_stale_overlay(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            filename="pack.json"
            pack={"concepts":[],"overlays":[{"id":"x","base_sha256":"wrong","changes":{}}]}
            (root/filename).write_text(json.dumps(pack))
            entry={"file":filename,"sha256":hashlib.sha256((root/filename).read_bytes()).hexdigest(),"count":0}
            (root/'manifest.json').write_text(json.dumps({"version":"test","packs":[entry]}))
            with self.assertRaises(ValueError):
                assemble([{"id":"x"}],root)
            entry['sha256']='forged';(root/'manifest.json').write_text(json.dumps({"version":"test","packs":[entry]}))
            with self.assertRaises(ValueError):
                assemble([{"id":"x"}],root)

    def test_independent_base_is_not_modified(self):
        self.assertEqual(self.base.find("可测空间").level, 1)
        self.assertTrue(all(not c.id.startswith("C14L") for c in self.base.concepts))

    def test_imported_scope_can_include_supplements(self):
        from unittest.mock import patch
        import math_mcts.knowledge as knowledge
        from dataclasses import asdict
        row=asdict(self.tree.find("加法交换律"))
        row.update(id="MOCK_IMPORT",module="Mathlib.Test.Basic",formal="example : True := trivial",
                   domain_cn="Algebra",domain_en="Algebra",prereq=[])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=gzip.compress(json.dumps({"concepts":[row]}).encode())
            (root/'shard.gz').write_bytes(data)
            (root/'manifest.json').write_text(json.dumps({"files":[{"shard":"shard.gz","shard_sha256":hashlib.sha256(data).hexdigest()}]}))
            with patch.object(knowledge,'IMPORTED_DIR',root),patch.object(knowledge,'_SHARD_INDEX',{'Mathlib.Test':['shard.gz']}):
                tree=KnowledgeTree.load_imported(module_prefix='Mathlib.Test',include_curated=True)
                self.assertIn('MOCK_IMPORT',tree.by_id)
                self.assertEqual(tree.get('MOCK_IMPORT').domain_cn,'代数')
                self.assertEqual(len(tree.concepts),len(self.tree.concepts)+1)

    def test_text_lengths_and_kinds(self):
        for row in self.report['authored']:
            c=self.tree.get(row['id'])
            self.assertLessEqual(len(c.definition),80)
            self.assertLessEqual(len(c.example),60)
            self.assertLessEqual(len(c.formulas),3)
            self.assertIn(c.kind,{'概念','公式','定理','方法','算法','思路','推论','分布','检验','引理'})


if __name__ == "__main__":
    unittest.main()
