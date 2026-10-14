"""Lean extractor request generator must avoid loading full Mathlib."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_knowledge_bank import fixture_db
from tools.generate_mathlib_extraction import generate


class GeneratorTests(unittest.TestCase):
    def test_module_only_import_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"math.sqlite"
            fixture_db(db)
            script=Path(tmp)/"Selected.lean"
            result=generate(db,script,limit=1,module_prefix="Mathlib.Algebra.Group")
            out=script.read_text()
            self.assertEqual(result["selected"],1)
            self.assertEqual(result["selected_source_modules"],
                             ["Mathlib.Algebra.Group.Basic"])
            self.assertIn("import Mathlib.Algebra.Group.Basic",out)
            self.assertNotIn("import Mathlib\n",out)
            self.assertIn('"source_statement_sha256"',out)
            self.assertIn('"source_id"',out)
            self.assertIn("IO.println missing.compress",out)
            self.assertNotIn('IO.println s!',out)

    def test_missing_module_does_not_silently_substitute_other_mathlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"math.sqlite"
            fixture_db(db)
            with self.assertRaisesRegex(ValueError,"No admissible"):
                generate(db,Path(tmp)/"bad.lean",limit=2,
                         module_prefix="Mathlib.Nonexistent.Module")
            with self.assertRaises(ValueError):
                generate(db,Path(tmp)/"bad.lean",limit=201)


if __name__=="__main__":
    unittest.main()
