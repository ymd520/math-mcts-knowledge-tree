"""Source-preserving Lean graph, module holdouts and adaptive route tests."""
from __future__ import annotations
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from math_mcts.lean_holdout import group_split, create_module_splits
from math_mcts.adaptive_search import choose_search_method,solve_adaptive
from math_mcts.reasoning import ProofGraph,load_reasoning_problem
from math_mcts.search_eval import mathematical_task_fixtures
from test_knowledge_bank import fixture_db
from math_mcts.knowledge_bank import classify_knowledge


class AdaptiveTests(unittest.TestCase):
    def test_real_mathematical_baselines_route_to_bfs(self):
        for name,data in mathematical_task_fixtures().items():
            with self.subTest(name=name):
                book,assumptions,goal=load_reasoning_problem(data)
                outcome=solve_adaptive(book,assumptions,goal,
                                       max_steps=12,iterations=200)
                self.assertEqual(outcome["method"],"bfs")
                self.assertTrue(outcome["solved"],outcome)
                self.assertTrue(outcome["replayed"],outcome)

    def test_incomplete_graph_never_routes_to_claimed_complete(self):
        incomplete=ProofGraph((),False,"edge_budget")
        method,reason=choose_search_method(incomplete,50)
        self.assertEqual(method,"beam")
        self.assertEqual(reason["completeness"],"not_guaranteed")
        complete=ProofGraph(tuple([None]*150),True,"fixed_point")
        self.assertEqual(choose_search_method(complete,1)[0],"beam")
        self.assertEqual(choose_search_method(complete,50)[0],"mcts")
        self.assertEqual(choose_search_method(complete,50,
                              exact_edge_threshold=200)[0],"bfs")

    def test_unsupported_budgets_rejected(self):
        data=mathematical_task_fixtures()["subset_transitivity"]
        book,assumptions,goal=load_reasoning_problem(data)
        with self.assertRaises(ValueError):
            solve_adaptive(book,assumptions,goal,iterations=0)
        with self.assertRaises(ValueError):
            choose_search_method(ProofGraph((),True,""),0,wide_frontier=0)


class HoldoutTests(unittest.TestCase):
    def test_same_module_keeps_same_split_and_is_reproducible(self):
        self.assertEqual(group_split("Mathlib.Algebra.Group.Basic"),
                         group_split("Mathlib.Algebra.Group.Basic"))
        self.assertIn(group_split("Mathlib.Topology.Basic"),
                      ("train","validation","test"))
        with self.assertRaises(ValueError):
            group_split("Unknown.Module")
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"math.sqlite"
            fixture_db(db)
            with sqlite3.connect(db) as cx:
                cx.execute("INSERT INTO source_registry VALUES(?,?,?,?,?,?)",
                  ("MTH02","separate_hash","Mathlib.Algebra.Group.Basic",
                   "fixed-commit","unreviewed_importance",None))
            outfile=Path(tmp)/"split.json"
            report=create_module_splits(db,outfile)
            self.assertEqual(report["source_theorems"],2)
            self.assertEqual(report["source_modules_spanning_multiple_splits"],0)
            with sqlite3.connect(db) as cx:
                groups=cx.execute("SELECT COUNT(DISTINCT split) FROM mathlib_holdout").fetchone()[0]
            self.assertEqual(groups,1)
            self.assertEqual(report,create_module_splits(db,outfile))
            self.assertEqual(json.loads(outfile.read_text()),report)


if __name__=="__main__":
    unittest.main()
