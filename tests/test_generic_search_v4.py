"""Generic MCTS v4: exact incremental grounding and bounded streamed branching.

All mathematical claims are relative to explicit reviewed typed Horn rules.
The stream and plateau modes are optional search heuristics, not proofs.
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.incremental_graph import build_incremental_graph
from math_mcts.mcts import Problem, mcts
from math_mcts.reasoning import Atom, ProofGraph, Rule, RuleBook
from math_mcts.hypergraph_closure import forward_certificate
from math_mcts.reasoning import verify_certificate


def a(name):
    return Atom(name)


def make_chain(n):
    nodes = [a(f"item_{i}") for i in range(n + 1)]
    rules = [Rule(f"r{i}", (nodes[i],), nodes[i + 1],
                  source="explicit math benchmark rule", status="reviewed")
             for i in range(n)]
    book = RuleBook({x.predicate: () for x in nodes}, {}, rules)
    return book, frozenset([nodes[0]]), nodes[-1]


class RuleIndexTests(unittest.TestCase):
    def test_sparse_chain_activates_only_changed_predicates(self):
        n = 120
        book, assumptions, goal = make_chain(n)
        graph, stats = build_incremental_graph(
            book, assumptions, goal, max_rounds=n + 3,
            max_edges=n + 20, return_stats=True)
        reference = ProofGraph.build(book, assumptions, goal,
                                    max_rounds=n + 3, max_edges=n + 20,
                                    strategy="reference")
        self.assertTrue(graph.complete)
        self.assertEqual(set(graph.edges), set(reference.edges))
        self.assertEqual(stats.selected_rules, n)
        self.assertLessEqual(stats.activated_rule_checks, n + 2)
        self.assertGreater(stats.avoided_rule_checks, n * n // 2)
        proof = forward_certificate(book, graph, assumptions, goal, max_steps=n)
        self.assertEqual(proof.proof_steps, n)
        self.assertTrue(verify_certificate(book, proof.certificate, assumptions, goal))

    def test_multiple_same_round_delta_anchors_count_once(self):
        a0, b, c, d = [a(s) for s in ("a", "b", "c", "d")]
        rules = [
            Rule("ab", (a0,), b, source="fixture", status="reviewed"),
            Rule("ac", (a0,), c, source="fixture", status="reviewed"),
            Rule("bc", (b, c), d, source="fixture", status="reviewed"),
        ]
        book = RuleBook({x.predicate: () for x in [a0, b, c, d]}, {}, rules)
        graph, stats = build_incremental_graph(
            book, frozenset([a0]), d, max_rounds=5, return_stats=True)
        reference = ProofGraph.build(book, frozenset([a0]), d,
                                    max_rounds=5, strategy="reference")
        self.assertEqual(set(graph.edges), set(reference.edges))
        self.assertTrue(graph.complete)
        self.assertEqual(stats.candidate_groundings, 3)
        self.assertGreaterEqual(stats.duplicate_delta_anchors_skipped, 1)

    def test_randomized_comparison_and_missing_premise(self):
        rng = random.Random(3705)
        for n in range(45):
            atoms = [a(f"p{i}") for i in range(9)]
            rules = [
                Rule(f"rule{i}",
                     tuple(rng.sample(atoms, rng.randrange(4))),
                     rng.choice(atoms), source="fixture", status="reviewed")
                for i in range(17)]
            book = RuleBook({x.predicate: () for x in atoms}, {}, rules)
            facts = frozenset(rng.sample(atoms, rng.randrange(4)))
            goal = rng.choice(atoms)
            with self.subTest(n=n):
                current, stats = build_incremental_graph(
                    book, facts, goal, max_rounds=20,
                    max_edges=500, return_stats=True)
                reference = ProofGraph.build(book, facts, goal,
                    max_rounds=20, max_edges=500, strategy="reference")
                self.assertEqual(set(current.edges), set(reference.edges))
                self.assertEqual(current.complete, reference.complete)
                self.assertEqual(current.reason, reference.reason)

    def test_truncated_graph_not_claimed_complete(self):
        book, assumptions, goal = make_chain(18)
        truncated = build_incremental_graph(book, assumptions, goal,
                                           max_edges=3)
        self.assertFalse(truncated.complete)
        self.assertEqual(truncated.reason, "edge_budget")


class StreamTests(unittest.TestCase):
    class Million(Problem):
        def __init__(self):
            self.yielded = 0
            self.solved = False
        def initial_state(self):
            return "root"
        def actions(self, state):
            raise AssertionError("Stream mode must never call eager actions")
        def iter_actions(self, state):
            if state != "root":
                return iter(())
            def source():
                for n in range(1_000_000):
                    self.yielded += 1
                    yield n
            return source()
        def step(self, state, action):
            return ("leaf", action)
        def terminal(self, state):
            return state != "root"
        def reward(self, state):
            if state == ("leaf", 0):
                self.solved = True
                return 1.0
            return 0.0
        def success_found(self):
            return self.solved

    def test_one_million_choices_only_one_consumed(self):
        p = self.Million()
        sequence, root = mcts(p, iterations=50, seed=3,
                             action_mode="stream", stop_on_success=True)
        self.assertEqual(sequence, [0])
        self.assertEqual(root.stats["yielded_actions"], 1)
        self.assertEqual(p.yielded, 1)
        self.assertEqual(root.stats["simulations"], 1)
        self.assertTrue(root.stats["early_stop"])
        self.assertEqual(root.stats["created_nodes"], 2)

    def test_stream_exhausts_finite_actions_safely(self):
        class Finite(self.Million):
            def iter_actions(self, state):
                return iter([0, 1]) if state == "root" else iter(())
        p = Finite()
        seq, root = mcts(p, iterations=30, seed=2, action_mode="stream")
        self.assertEqual(root.stats["yielded_actions"], 2)
        self.assertGreaterEqual(root.stats["stream_exhausted_nodes"], 1)
        self.assertEqual(root.stats["simulations"], 30)
        self.assertTrue(seq)

    def test_stream_search_descends_without_enumerating_root(self):
        class Deep(Problem):
            def initial_state(self):
                return 0
            def actions(self, state):
                raise AssertionError("No eager action")
            def iter_actions(self, state):
                if state == 0:
                    return iter(range(500_000))
                if state == 1:
                    return iter([1])
                return iter(())
            def step(self, state, action):
                return state + 1
            def terminal(self, state):
                return state == 2
            def reward(self, state):
                return 1.0 if state == 2 else 0.0
        _, root = mcts(Deep(), iterations=40, seed=3, action_mode="stream",
                       max_depth=3)
        self.assertTrue(any(node.children for node in root.children))
        self.assertLess(root.stats["yielded_actions"], 40)

    def test_compatibility_and_invalid_options(self):
        p = self.Million()
        with self.assertRaisesRegex(ValueError, "normalized PUCT"):
            mcts(p, action_mode="stream", policy="puct")
        with self.assertRaisesRegex(ValueError, "action_mode"):
            mcts(p, action_mode="unknown")
        with self.assertRaisesRegex(ValueError, "plateau_patience"):
            mcts(p, plateau_patience=0)
        with self.assertRaisesRegex(ValueError, "min_plateau_iterations"):
            mcts(p, min_plateau_iterations=0)

    def test_opt_in_plateau_and_no_default_early_stop(self):
        class Constant(Problem):
            def initial_state(self):
                return "root"
            def actions(self, state):
                return ["leaf"] if state == "root" else []
            def step(self, state, action):
                return action
            def terminal(self, state):
                return state == "leaf"
            def reward(self, state):
                return 0.0
        _, shortened = mcts(Constant(), iterations=100,
                            plateau_patience=7, min_plateau_iterations=10, seed=1)
        self.assertEqual(shortened.stats["simulations"], 10)
        self.assertTrue(shortened.stats["plateau_stop"])
        _, default = mcts(Constant(), iterations=31, seed=1)
        self.assertEqual(default.stats["simulations"], 31)
        self.assertFalse(default.stats["plateau_stop"])


class SelectionBackupSeparationTests(unittest.TestCase):
    def test_max_backup_retains_mean_and_best_statistics(self):
        class MaxProblem(Problem):
            value_op = "max"
            def initial_state(self):
                return "root"
            def actions(self, state):
                return ["low", "high"] if state == "root" else []
            def step(self, state, action):
                return action
            def terminal(self, state):
                return state != "root"
            def reward(self, state):
                return {"low": 0.2, "high": 0.9}.get(state, 0.0)

        _, root = mcts(MaxProblem(), iterations=80, seed=9,
                       selection_value="mean")
        self.assertEqual(root.stats["selection_value"], "mean")
        self.assertEqual(root.visits, root.stats["simulations"])
        self.assertAlmostEqual(root.best, 0.9)
        self.assertGreaterEqual(root.mean, 0.2)
        self.assertLessEqual(root.mean, 0.9)

    def test_max_sample_selection_is_available_for_mean_backup(self):
        class MeanProblem(Problem):
            def initial_state(self):
                return "root"
            def actions(self, state):
                return ["a", "b"] if state == "root" else []
            def step(self, state, action):
                return action
            def terminal(self, state):
                return state != "root"
            def reward(self, state):
                return {"a": 0.1, "b": 0.8}.get(state, 0.0)

        _, root = mcts(MeanProblem(), iterations=50, seed=4,
                       selection_value="max")
        self.assertEqual(root.stats["selection_value"], "max")
        self.assertAlmostEqual(root.best, 0.8)
        self.assertGreaterEqual(root.mean, 0.1)
        self.assertLessEqual(root.mean, 0.8)

    def test_invalid_selection_value_rejected(self):
        class Empty(Problem):
            def initial_state(self):
                return 0
            def actions(self, state):
                return []
            def step(self, state, action):
                return state
            def terminal(self, state):
                return True
            def reward(self, state):
                return 0.0

        with self.assertRaisesRegex(ValueError, "selection_value"):
            mcts(Empty(), iterations=1, selection_value="unknown")


if __name__ == "__main__":
    unittest.main()
