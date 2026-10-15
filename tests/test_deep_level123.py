"""Adversarial audit of individually authored Level 1–3 multidomain knowledge."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.knowledge import KnowledgeTree
from math_mcts.catalog import PACK_DIR,name_key,assemble
from math_mcts.version import CATALOG_VERSION

PACK="level123_multidomain_20261014.json"
PREFIX="C26D"


class Level123DeepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=KnowledgeTree.load(include_supplements=False)
        cls.tree=KnowledgeTree.load()
        cls.pack=json.loads((PACK_DIR/PACK).read_text(encoding="utf-8"))
        cls.rows=cls.pack["concepts"]

    def test_balanced_105_source_grounded_math_records(self):
        self.assertEqual(len(self.rows),105)
        by=Counter((r["domain_cn"],r["level"]) for r in self.rows)
        self.assertEqual(len({x for x,_ in by}),7)
        for domain in {x for x,_ in by}:
            for level in (1,2,3):
                self.assertEqual(by[(domain,level)],5)
        self.assertEqual(dict(Counter(r["level"] for r in self.rows)),{1:35,2:35,3:35})
        self.assertEqual(self.tree.meta["version"],CATALOG_VERSION)
        self.assertEqual(len(self.tree.concepts),
                         self.base.inventory()["total"]+self.tree.meta["catalog_added"])
        self.assertEqual(self.tree.check_integrity(),[])
        oldnames={name_key(c.cn):[] for c in self.base.concepts}
        for c in self.base.concepts:
            oldnames[name_key(c.cn)].append(c.id)
        clashes=[(r["id"],r["cn"],oldnames[name_key(r["cn"])])
                 for r in self.rows if name_key(r["cn"]) in oldnames]
        self.assertEqual(clashes,[],f"New entries collide with base: {clashes!r}")
        # This test owns the 105-row pack, not unrelated duplicate names
        # already present in separate curated/deep-core source bundles.
        # Check that each of THESE 105 names is unique in the actual catalog.
        merged_names=Counter(name_key(c.cn) for c in self.tree.concepts)
        collisions={r["cn"]:merged_names[name_key(r["cn"])]
                    for r in self.rows if merged_names[name_key(r["cn"])] != 1}
        self.assertEqual(collisions, {}, "105-row pack introduced an ambiguous name")

    def test_conditions_are_bound_and_no_false_lean_certification(self):
        seen=set()
        ids={r["id"] for r in self.rows}
        for row in self.rows:
            with self.subTest(knowledge=row["id"]):
                self.assertTrue(row["id"].startswith(PREFIX))
                self.assertNotIn(name_key(row["cn"]),seen)
                seen.add(name_key(row["cn"]))
                self.assertTrue(row["assumptions"].strip())
                self.assertTrue(row["conclusion"].strip())
                self.assertEqual(len(row["formulas"]),1)
                self.assertTrue(row["original_metadata"]["边界/反例"].strip())
                self.assertTrue(row["original_metadata"]["跨领域应用"].strip())
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertIn("非逐条",row["source_locator"])
                self.assertIn(row["verification_status"],
                              ("editorial_mathematical_statement_not_formal_proof",))
                self.assertEqual(row["reference_relation"],
                                 "topic_reference_not_statement_certification")
                self.assertEqual(row["statement_sha256"],hashlib.sha256((
                     row["assumptions"]+"\n"+row["conclusion"]+"\n"+row["formulas"][0]
                     ).encode("utf-8")).hexdigest())
                self.assertIn("重要",row["tags"])
                self.assertNotIn("verified_by_kernel",row)
                self.assertEqual(self.tree.get(row["id"]).statement_sha256,
                                 row["statement_sha256"])
                self.assertTrue(all(p in ids for p in row["prereq"]))

    def test_precondition_edges_not_falsely_promoted_as_proofs(self):
        rowmap={r["id"]:r for r in self.rows}
        cross=0
        edges=0
        for r in self.rows:
            for dep in r["prereq"]:
                edges+=1
                self.assertLess(int(dep[-4:]),int(r["id"][-4:]),
                                "No circular or forward automatic knowledge dependency")
                cross+=rowmap[dep]["domain_cn"]!=r["domain_cn"]
                self.assertIn("not_formal",r["prereq_status"])
        self.assertGreaterEqual(edges,35)
        self.assertGreaterEqual(cross,1)
        self.assertNotIn("formal_kernel_verified",str(self.pack))

    def test_sha_locked_pack_fails_closed_when_tampered(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            src=PACK_DIR/"manifest.json"
            origin=json.loads(src.read_text(encoding="utf-8"))
            copy=Path(directory)
            manifest=origin.copy()
            manifest["packs"]=[next(r for r in origin["packs"] if r["file"]==PACK)]
            (copy/"manifest.json").write_text(json.dumps(manifest))
            data=(PACK_DIR/PACK).read_text(encoding="utf-8")
            (copy/PACK).write_text(data.replace("差集的交互斥分解","伪造的数学结论",1))
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                assemble([],copy)


if __name__=="__main__":
    unittest.main()
