"""Adversarial equality checks for semi-naive vs independent reference joins.

Tests deliberately cover cycles, multi-premise joins, repeated variables,
constants, empty premises, candidate-only rules and incomplete budgets.
"""
from __future__ import annotations

import random
import sys
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.reasoning import Atom, Rule, RuleBook, ProofGraph, derive, verify_certificate
from math_mcts.incremental_graph import build_incremental_graph
from math_mcts.hypergraph_closure import forward_certificate
from math_mcts.search_eval import mathematical_task_fixtures
from math_mcts.reasoning import load_reasoning_problem


def p(name, *values):
    return Atom(name, tuple(values))


def compare(book, facts, goal, *, rounds=60, edges=3000):
    old = ProofGraph.build(book, frozenset(facts), goal, rounds, edges,
                           strategy="reference")
    new, stats = build_incremental_graph(book, facts, goal, max_rounds=rounds,
                                         max_edges=edges, return_stats=True)
    if old.complete:
        assert new.complete and set(old.edges) == set(new.edges), (
            old.reason, new.reason, len(old.edges), len(new.edges))
    assert len(new.edges) == len(set(new.edges))
    assert stats.unique_edges == len(new.edges)
    assert stats.selected_rules <= len(book.rules)
    assert stats.status == "ground_reviewed_rules_only"
    proof = forward_certificate(book, new, frozenset(facts), goal)
    if proof.certificate:
        assert verify_certificate(book, proof.certificate, frozenset(facts), goal)
    return old, new, stats


class SemiNaiveTests(unittest.TestCase):
    def test_shared_math_fixtures_identical_ground_edges(self):
        for name, spec in mathematical_task_fixtures().items():
            with self.subTest(name=name):
                book, facts, goal = load_reasoning_problem(spec)
                old, new, stats = compare(book, facts, goal)
                self.assertEqual(len(new.edges), len(old.edges))
                self.assertTrue(new.complete)
                self.assertEqual(new.reason, "fixed_point")
                result = derive(book, facts, goal, iterations=1)
                self.assertEqual(result.status, "derived_relative_to_rules")
                self.assertTrue(verify_certificate(book, result.certificate,
                                                    facts, goal))

    def test_variable_join_with_multiple_positions_and_constants(self):
        objects = {"a": "T", "b": "T", "c": "T", "d": "T"}
        signatures = {"link": ("T", "T"), "diag": ("T",), "good": ("T",)}
        r = Rule("trans", (p("link", "?x", "?y"), p("link", "?y", "?z")),
                 p("link", "?x", "?z"),
                 (("?x", "T"), ("?y", "T"), ("?z", "T")),
                 "synthetic typed example", "reviewed")
        s = Rule("diag", (p("link", "?x", "?x"),), p("diag", "?x"),
                 (("?x", "T"),), "synthetic", "reviewed")
        t = Rule("good", (p("diag", "?x"), p("link", "?x", "d")),
                 p("good", "?x"), (("?x", "T"),), "synthetic", "reviewed")
        book = RuleBook(signatures, objects, [r, s, t])
        facts = frozenset([p("link", "a", "b"), p("link", "b", "c"),
                           p("link", "c", "d")])
        old, new, stats = compare(book, facts, p("good", "a"))
        self.assertGreater(len(new.edges), 10)
        self.assertTrue(new.complete)
        self.assertLess(stats.premise_match_attempts, 20000)

    def test_nullary_rule_from_empty_assumptions(self):
        book = RuleBook({"a": (), "b": ()}, {}, [
            Rule("seed", (), p("a"), source="synthetic", status="reviewed"),
            Rule("follow", (p("a"),), p("b"), source="synthetic", status="reviewed")])
        old, new, stats = compare(book, [], p("b"))
        self.assertEqual(set(old.edges), set(new.edges))
        self.assertEqual(len(new.edges), 2)
        self.assertEqual(derive(book, [], p("b"), iterations=1).applied_rules, 2)

    def test_candidates_never_become_active(self):
        book = RuleBook({"p": (), "q": ()}, {}, [
            Rule("unreviewed", (p("p"),), p("q"), source="candidate",
                 status="candidate")])
        old, new, stats = compare(book, [p("p")], p("q"))
        self.assertEqual(len(new.edges), 0)
        self.assertEqual(derive(book, [p("p")], p("q"), iterations=2).status,
                         "not_derivable_from_reviewed_ground_rules")

    def test_randomized_small_ground_horn_graphs(self):
        rng = random.Random(90217)
        atoms = [p(f"p{i}") for i in range(12)]
        for case in range(100):
            rules = []
            for i in range(30):
                premises = tuple(rng.sample(atoms, rng.randrange(4)))
                conclusion = rng.choice(atoms)
                rules.append(Rule(f"r{i}", premises, conclusion,
                                  source="synthetic", status="reviewed"))
            book = RuleBook({x.predicate: () for x in atoms}, {}, rules)
            facts = frozenset(rng.sample(atoms, rng.randrange(5)))
            goal = rng.choice(atoms)
            with self.subTest(case=case):
                old, new, _ = compare(book, facts, goal)
                self.assertEqual(set(old.edges), set(new.edges))
                self.assertEqual(old.complete, new.complete)

    def test_budget_status_cannot_claim_completeness(self):
        nodes = [p(f"q{i}") for i in range(12)]
        book = RuleBook({x.predicate: () for x in nodes}, {}, [
            Rule(f"r{i}", (nodes[i],), nodes[i + 1],
                 source="synthetic", status="reviewed") for i in range(11)])
        limited = ProofGraph.build(book, frozenset([nodes[0]]), nodes[-1],
                                   max_rounds=3, strategy="incremental")
        self.assertFalse(limited.complete)
        self.assertEqual(limited.reason, "round_budget")
        limited = ProofGraph.build(book, frozenset([nodes[0]]), nodes[-1],
                                   max_edges=2, strategy="incremental")
        self.assertFalse(limited.complete)
        self.assertEqual(limited.reason, "edge_budget")
        self.assertIsNone(derive(book, [nodes[0]], nodes[-1], iterations=2,
                                 max_rounds=3).certificate)

    def test_reject_invalid_strategy(self):
        atom = p("a")
        book = RuleBook({"a": ()}, {}, [])
        with self.assertRaisesRegex(ValueError, "strategy"):
            ProofGraph.build(book, frozenset(), atom, strategy="guess")
        with self.assertRaisesRegex(ValueError, "budgets"):
            ProofGraph.build(book, frozenset(), atom, strategy="incremental",
                             max_rounds=0)

    def test_uniform_long_chain_avoids_full_rescans(self):
        depth = 100
        nodes = [p(f"q{i}") for i in range(depth + 1)]
        rules = [Rule(f"r{i}", (nodes[i],), nodes[i+1], source="synthetic",
                      status="reviewed") for i in range(depth)]
        book = RuleBook({x.predicate: () for x in nodes}, {}, rules)
        old = ProofGraph.build(book, frozenset([nodes[0]]), nodes[-1],
                               max_rounds=depth+3, strategy="reference")
        new, stats = build_incremental_graph(book, [nodes[0]], nodes[-1],
                    max_rounds=depth+3, return_stats=True)
        self.assertTrue(new.complete)
        self.assertEqual(set(old.edges), set(new.edges))
        self.assertEqual(stats.unique_edges, depth)
        self.assertLessEqual(stats.premise_match_attempts, depth * 2)


if __name__ == "__main__":
    unittest.main()
