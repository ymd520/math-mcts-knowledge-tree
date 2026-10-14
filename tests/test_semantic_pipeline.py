"""Independent adversarial tests of graph safety and search comparisons."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.reasoning import (Rule, RuleBook, Atom, load_reasoning_problem,
                                 ProofGraph, ProofState, DerivationProblem)
from math_mcts.semantic_graph import build_semantic_graph, SemanticGraph
from math_mcts.search_eval import (
    mathematical_task_fixtures, benchmark_rule_problem, solve_baseline,
)


class SemanticGraphTests(unittest.TestCase):
    def graph_book(self):
        signatures={"P":("S",), "Q":("S",), "R":("S",),
                    "Wrong":("T",)}
        objects={"x":"S","z":"T"}
        rules=[
            Rule("p_to_q", (Atom("P",("?x",)),),Atom("Q",("?x",)),
                 (("?x","S"),),source="synthetic explicit proof rule",status="reviewed"),
            Rule("q_to_r", (Atom("Q",("?y",)),),Atom("R",("?y",)),
                 (("?y","S"),),source="synthetic explicit proof rule",status="reviewed"),
            Rule("wrong_sort", (Atom("Wrong",("?z",)),),Atom("Wrong",("?z",)),
                 (("?z","T"),),source="synthetic",status="candidate"),
        ]
        return RuleBook(signatures,objects,rules)

    def test_typed_adjacency_and_remaining_conditions(self):
        book=self.graph_book()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"graph.sqlite"
            summary=build_semantic_graph(book,path)
            self.assertEqual(summary["reviewed_rules"],2)
            self.assertEqual(summary["candidate_edges"],1)
            g=SemanticGraph(path,book=book)
            n=g.neighbors("p_to_q")
            self.assertEqual(len(n),1)
            self.assertEqual(n[0]["consumer"],"q_to_r")
            self.assertEqual(n[0]["signature"],["S"])
            self.assertEqual(n[0]["status"],"typed_possible_composition_not_proof")
            self.assertEqual(g.neighbors("q_to_r",direction="backward")[0]["producer"],
                             "p_to_q")
            self.assertEqual(g.backward_relevant_rules(book,"R"),["p_to_q","q_to_r"])
            self.assertEqual(g.neighbors("wrong_sort"),[])
            with self.assertRaises(ValueError):
                g.neighbors("p_to_q",limit=0)

    def test_old_rulebook_graph_rejected(self):
        book=self.graph_book()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"graph.sqlite"
            build_semantic_graph(book,path)
            changed=RuleBook(book.signatures,book.objects,
                [Rule("p_to_q",(Atom("P",("?x",)),),Atom("Q",("?x",)),
                      (("?x","S"),),source="new source",status="reviewed")])
            with self.assertRaisesRegex(ValueError,"stale"):
                SemanticGraph(path,book=changed)

    def test_candidate_rules_never_get_graph_edges(self):
        book=self.graph_book()
        self.assertEqual(len(book.candidates),1)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"graph.sqlite"
            build_semantic_graph(book,path)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM rules WHERE id='wrong_sort'").fetchone()[0],0)

    def test_invalid_predicate_rejected(self):
        book=self.graph_book()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"graph.sqlite"
            build_semantic_graph(book,path)
            with self.assertRaisesRegex(ValueError,"Unknown"):
                SemanticGraph(path,book=book).backward_relevant_rules(book,"Z")


class BaselineTests(unittest.TestCase):
    def test_all_elementary_math_tasks_bfs_beam_prove_relative_to_rules(self):
        for name, data in mathematical_task_fixtures().items():
            with self.subTest(name=name):
                report=benchmark_rule_problem(data,iterations=220,max_steps=12)
                self.assertTrue(report["graph_complete"])
                methods={row["method"]:row for row in report["methods"]}
                self.assertTrue(methods["bfs"]["solved"],report)
                self.assertTrue(methods["beam"]["solved"],report)
                self.assertTrue(methods["bfs"]["certificate_replayed"])
                self.assertTrue(methods["beam"]["certificate_replayed"])
                # Stochastic MCTS may or may not solve under the finite budget;
                # when successful, its returned certificate must replay.
                if methods["mcts"]["solved"]:
                    self.assertTrue(methods["mcts"]["certificate_replayed"])

    def test_absent_premise_never_yields_a_certificate(self):
        data=mathematical_task_fixtures()["membership_transport"]
        data["assumptions"]=[x for x in data["assumptions"]
                            if x["args"]!=["C","D"]]
        book, assumptions,goal=load_reasoning_problem(data)
        outcome=solve_baseline(book,assumptions,goal,method="bfs",
                               max_steps=10,max_expansions=100)
        self.assertFalse(outcome.solved)
        self.assertIsNone(outcome.certificate)

    def test_indexed_actions_equal_reference_full_scan(self):
        # Compare candidate eligibility against a full scan for all 2^4
        # subsets of four ground atoms. The index must change only speed.
        from itertools import combinations
        data=mathematical_task_fixtures()["membership_transport"]
        book,assumptions,goal=load_reasoning_problem(data)
        graph=ProofGraph.build(book,assumptions,goal)
        problem=DerivationProblem(graph,assumptions,goal,max_steps=20)
        universe=sorted(assumptions | {e.conclusion for e in graph.edges})
        for size in range(len(universe)+1):
            for group in combinations(universe,size):
                state=ProofState(frozenset(group))
                got=problem.actions(state)
                expected=[e for e in graph.edges if e.conclusion not in state.facts
                          and set(e.premises)<=state.facts] if goal not in state.facts else []
                self.assertEqual(got,expected)

    def test_action_cache_capacity_is_bounded(self):
        data=mathematical_task_fixtures()["divisibility_transitivity"]
        book,assumptions,goal=load_reasoning_problem(data)
        graph=ProofGraph.build(book,assumptions,goal)
        problem=DerivationProblem(graph,assumptions,goal,max_steps=20)
        problem._cache_capacity=2
        for edge in graph.edges:
            problem.actions(ProofState(assumptions | {edge.conclusion}))
        self.assertLessEqual(len(problem._actions),2)

    def test_zero_budget_and_unsupported_method_rejected(self):
        data=mathematical_task_fixtures()["subset_transitivity"]
        book,ass,goal=load_reasoning_problem(data)
        with self.assertRaises(ValueError):
            solve_baseline(book,ass,goal,max_expansions=0)
        with self.assertRaises(ValueError):
            solve_baseline(book,ass,goal,method="unknown")


if __name__=="__main__":
    unittest.main()
