"""Exact-source attribution, conservative file header author parsing."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from math_mcts.attribution import (
    source_credit,module_source_path,module_source_url,parse_file_header,
    build_attribution_index,attribution_by_id,
)
from math_mcts.knowledge_bank import classify_knowledge,KnowledgeBank
from math_mcts.source_registry import SOURCE_COMMIT


class SourceCreditTests(unittest.TestCase):
    def test_every_knowledge_record_is_attributed_conservatively(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/"index.sqlite"
            fixture_db(db)
            classify_knowledge(db)
            report=build_attribution_index(db)
            self.assertEqual(report["total_attributed_records"],3)
            self.assertEqual(report["by_source_kind"],
                             {"curated":1,"imported_standard_card":1,
                              "upstream_theorem":1})
            upstream=attribution_by_id(db,"MTH01")
            self.assertEqual(upstream["source_commit"],SOURCE_COMMIT)
            self.assertEqual(upstream["license"],"Apache-2.0")
            self.assertEqual(upstream["source_project"],"mathlib4")
            self.assertIn("Mathlib/Algebra/Group/Basic.lean",
                          upstream["source_module_url"])
            self.assertEqual(upstream["original_theorem_author"],
                             "not_individually_identified")
            self.assertEqual(upstream["mathematics_originality_claim"],"none")
            standard=attribution_by_id(db,"STD01")
            self.assertEqual(standard["license"],"verify_original_source_license")
            curated=KnowledgeBank(db).get("CUR01")
            self.assertEqual(curated["attribution"]["mathematics_originality_claim"],"none")
            searched=KnowledgeBank(db).search("smul")
            self.assertEqual(searched[0]["attribution"]["license"],"Apache-2.0")
            self.assertEqual(build_attribution_index(db),report)

    def test_upstream_module_urls_are_pinned_and_injection_safe(self):
        url=module_source_url("Mathlib.Algebra.Group.Basic")
        self.assertIn(SOURCE_COMMIT,url)
        self.assertTrue(url.endswith("Mathlib/Algebra/Group/Basic.lean"))
        for bad in ("Mathlib.X../PASSWORD", "Mathlib../Other",
                    "https://example.com", "Mathlib..Basic"):
            with self.subTest(module=bad):
                with self.assertRaises(ValueError):
                    module_source_path(bad)

    def test_file_authors_are_not_theorem_discoverer(self):
        source="""/-
Copyright (c) 2014 Jeremy Avigad. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Jeremy Avigad, Leonardo de Moura, Simon Hudon, Mario Carneiro
-/
module
"""
        header=parse_file_header(source)
        self.assertEqual(len(header["module_header_authors"]),4)
        self.assertEqual(header["attribution_scope"],
                         "module_file_header_not_individual_theorem")
        self.assertEqual(parse_file_header("theorem hello : True := trivial")
                         ["module_header_authors"],[])


if __name__=="__main__":
    unittest.main()
