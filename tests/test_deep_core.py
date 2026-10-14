"""Adversarial content audit for deep Level1–3 cards and source boundaries."""
import collections
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.knowledge import KnowledgeTree
from math_mcts.catalog import name_key
from math_mcts.deep_core import SEED_PATH,load_deep_core


class DeepLevel123Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=KnowledgeTree.load(include_supplements=False)
        cls.tree=KnowledgeTree.load()

    def test_all_seven_domains_all_three_levels_even_coverage(self):
        report=self.tree.meta
        self.assertEqual(report["deep_core_added"],141)
        self.assertEqual(report["deep_core_by_level"],{1:44,2:45,3:52})
        self.assertEqual(len(report["deep_core_by_domain"]),7)
        self.assertEqual(report["deep_core_by_domain"],{"数学基础":20,"代数":20,"分析":21,"几何与拓扑":20,"概率与统计":21,"离散数学":19,"计算与优化":20})
        self.assertEqual(report["catalog_version"],"1.14.0")
        self.assertEqual(report["deep_core_seed_sha256"],
                         hashlib.sha256(SEED_PATH.read_bytes()).hexdigest())
        self.assertEqual(self.tree.check_integrity(),[])

    def test_proof_idea_counterexample_and_source_in_every_card(self):
        deep=[c for c in self.tree.concepts if c.id.startswith("D123_")]
        self.assertEqual(len(deep),141)
        names=[name_key(c.cn) for c in self.tree.concepts]
        self.assertEqual(len(names)-len(set(names)),
                         len([name_key(c.cn) for c in self.base.concepts])-
                         len(set(name_key(c.cn) for c in self.base.concepts)))
        for c in deep:
            with self.subTest(name=c.cn):
                self.assertIn(c.level,(1,2,3))
                self.assertTrue(c.assumptions and c.conclusion)
                self.assertTrue(c.formulas and c.proof_idea and c.misuse_counterexample)
                self.assertTrue(c.source_url.startswith("https://"))
                self.assertIn("主题参考",c.source_locator)
                self.assertIn("重要",c.tags)
                self.assertIn("人工审核待完成",c.tags)
                self.assertEqual(c.reference_relation,
                                 "topic_reference_not_statement_certification")
                self.assertEqual(c.verification_status,
                                 "authored_standard_fact_not_kernel_verified")
                self.assertEqual(c.curation_status,
                                 "editorial_candidate_not_independently_reviewed")
                self.assertIn("not_new_discovery",c.knowledge_origin)
                self.assertIn("误用与反例",c.card())
                self.assertIn("证明/求解思路",c.card())
                self.assertEqual(c.statement_sha256,hashlib.sha256(
                    (c.assumptions+"\n"+c.conclusion+"\n"+c.formulas[0]).encode()).hexdigest())
                for prior in c.prereq:
                    self.assertIn(prior,self.tree.by_id)
                    self.assertLessEqual(self.tree.get(prior).level,c.level)

    def test_cross_domain_links_are_explicit_and_finite(self):
        edges=[(self.tree.get(p),c)
               for c in self.tree.concepts if c.id.startswith("D123_")
               for p in c.prereq]
        across=[(a,b) for a,b in edges if a.domain_cn!=b.domain_cn]
        self.assertGreaterEqual(len(across),3)
        self.assertTrue(any(a.domain_cn=="数学基础" and b.domain_cn=="计算与优化"
                            for a,b in across))
        self.assertTrue(any(a.domain_cn=="分析" and b.domain_cn=="计算与优化"
                            for a,b in across))

    def test_invalid_reference_and_duplicate_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake=Path(tmp)/"bad.tsv"
            fake.write_text("@1|代数|教材|章节|LIN\n"+
                "假定命题|Demo|有x|结论|x=x|直接代入|无需条件|取1|不存在的前提\n")
            with self.assertRaisesRegex(ValueError,"Unknown explicitly"):
                load_deep_core(existing_rows=[],seed=fake)
            fake.write_text("@1|代数|教材|章节|LIN\n"+
                "假定命题|Demo|有x|结论|x=x|直接代入|无需条件|取1|\n"+
                "假定命题|Demo|有x|结论|x=x|直接代入|无需条件|取1|\n")
            with self.assertRaisesRegex(ValueError,"Duplicate"):
                load_deep_core(existing_rows=[],seed=fake)


if __name__=="__main__":
    unittest.main()
