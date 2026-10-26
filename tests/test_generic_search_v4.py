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


class TrajectoryTraceTests(unittest.TestCase):
    class TinyTree(Problem):
        def initial_state(self):
            return "root"
        def actions(self, state):
            return {"root": ["A", "B"], "A": ["finish_A"],
                    "B": ["finish_B"]}.get(state, [])
        def step(self, state, action):
            return action if action in {"A", "B"} else action.removeprefix("finish_") + "_done"
        def terminal(self, state):
            return state.endswith("_done")
        def reward(self, state):
            return 1.0 if state == "A_done" else 0.0

    def test_best_rollout_trace_replays_to_recorded_score(self):
        problem = self.TinyTree()
        _, root = mcts(problem, iterations=100, max_depth=4, seed=17)
        self.assertTrue(root.stats["best_trajectory_complete"])
        self.assertEqual(root.stats["best_observed_value"], 1.0)
        state = problem.initial_state()
        for action in root.best_trajectory:
            state = problem.step(state, action)
        self.assertTrue(problem.terminal(state))
        self.assertEqual(problem.reward(state), root.best_observed)
        self.assertEqual(root.stats["best_trajectory_depth"],
                         len(root.best_trajectory))

    def test_custom_opaque_simulator_is_not_claimed_as_complete_trace(self):
        class Opaque(Problem):
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
            def simulate(self, state, rng, max_depth):
                return 0.75

        _, root = mcts(Opaque(), iterations=1, seed=1)
        self.assertFalse(root.stats["best_trajectory_complete"])
        self.assertEqual(root.stats["best_observed_value"], 0.75)
        self.assertEqual(root.best_trajectory, ["leaf"])


class CanonicalStateTests(unittest.TestCase):
    def test_duplicate_sibling_states_and_ancestral_cycles_are_skipped(self):
        class Loopy(Problem):
            def initial_state(self):
                return "root"
            def actions(self, state):
                return (["to_A", "alias_A", "loop"] if state == "root"
                        else ["back"] if state == "A" else [])
            def step(self, state, action):
                if state == "root":
                    return {"to_A": "A", "alias_A": "A",
                            "loop": "root"}[action]
                return "root"
            def terminal(self, state):
                return False
            def reward(self, state):
                return 0.0

        _, root = mcts(Loopy(), iterations=80, max_depth=5, seed=11,
                       state_key=lambda state: state)
        self.assertEqual(len(root.children), 1)
        self.assertGreaterEqual(root.stats["duplicate_states_skipped"], 1)
        self.assertGreaterEqual(root.stats["cycle_edges_skipped"], 1)

    def test_state_key_must_return_hashable_identity(self):
        class Unhashable(Problem):
            def initial_state(self):
                return []
            def actions(self, state):
                return []
            def step(self, state, action):
                return state
            def terminal(self, state):
                return True
            def reward(self, state):
                return 0.0

        with self.assertRaisesRegex(ValueError, "hashable"):
            mcts(Unhashable(), iterations=1, state_key=lambda state: state)


class SearchBudgetTests(unittest.TestCase):
    def test_node_budget_caps_tree_growth_but_allows_evaluation(self):
        class Wide(Problem):
            def initial_state(self):
                return "root"
            def actions(self, state):
                return list(range(100)) if state == "root" else []
            def step(self, state, action):
                return ("leaf", action)
            def terminal(self, state):
                return state != "root"
            def reward(self, state):
                return 0.0

        _, root = mcts(Wide(), iterations=20, max_nodes=3, seed=3)
        self.assertLessEqual(root.stats["created_nodes"], 3)
        self.assertEqual(root.stats["simulations"], 20)
        self.assertTrue(root.stats["node_budget_exhausted"])

    def test_zero_time_budget_stops_before_first_simulation(self):
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

        _, root = mcts(Empty(), iterations=100, time_budget_seconds=0.0)
        self.assertEqual(root.stats["simulations"], 0)
        self.assertEqual(root.stats["stop_reason"], "time_budget")
        self.assertGreaterEqual(root.stats["elapsed_seconds"], 0.0)

    def test_invalid_budgets_are_rejected(self):
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

        with self.assertRaisesRegex(ValueError, "max_nodes"):
            mcts(Empty(), max_nodes=0)
        with self.assertRaisesRegex(ValueError, "time_budget_seconds"):
            mcts(Empty(), time_budget_seconds=float("nan"))
        with self.assertRaisesRegex(ValueError, "time_budget_seconds"):
            mcts(Empty(), time_budget_seconds=True)
        with self.assertRaisesRegex(ValueError, "iterations"):
            mcts(Empty(), iterations=True)
        with self.assertRaisesRegex(ValueError, "max_depth"):
            mcts(Empty(), max_depth=1.5)
        with self.assertRaisesRegex(ValueError, "finite numbers"):
            mcts(Empty(), exploration=float("nan"))


class PUCTAdmissionFairnessTests(unittest.TestCase):
    class WeightedWide(Problem):
        value_op = "max"

        def initial_state(self):
            return "root"

        def actions(self, state):
            return list(range(40)) if state == "root" else []

        def action_weight(self, state, action):
            return float(action + 1)

        def step(self, state, action):
            return ("leaf", action)

        def terminal(self, state):
            return state != "root"

        def reward(self, state):
            return 0.0

    def test_epsilon_admission_is_seeded_and_reaches_low_prior_actions(self):
        def run():
            _, root = mcts(
                self.WeightedWide(), iterations=80, seed=31, policy="puct",
                widening_k=1.5, widening_alpha=0.5, admission_epsilon=1.0,
                max_depth=2,
            )
            return [child.action for child in root.children], root.stats

        first_actions, stats = run()
        second_actions, second_stats = run()
        self.assertEqual(first_actions, second_actions)
        self.assertEqual(stats["puct_random_admissions"],
                         second_stats["puct_random_admissions"])
        self.assertGreater(stats["puct_random_admissions"], 0)
        self.assertTrue(any(action < 10 for action in first_actions))
        self.assertEqual(stats["admission_epsilon"], 1.0)

    def test_admission_epsilon_validation(self):
        with self.assertRaisesRegex(ValueError, "admission_epsilon"):
            mcts(self.WeightedWide(), policy="puct", admission_epsilon=-0.1)
        with self.assertRaisesRegex(ValueError, "admission_epsilon"):
            mcts(self.WeightedWide(), policy="puct", admission_epsilon=float("nan"))


from math_mcts.product_defect import FiniteGroupProductDefect, ProductDefectSearchProblem


class IncrementalProductDefectTests(unittest.TestCase):
    @staticmethod
    def d8_multiply(a, b):
        i, s = a
        j, t = b
        return ((i + (-1 if s else 1) * j) % 4, s ^ t)

    def test_cyclic_group_swap_matches_full_recomputation(self):
        group = range(8)
        mul = lambda a, b: (a + b) % 8
        evaluator = FiniteGroupProductDefect(group, mul, {0, 1, 3}, compact_every=2)
        state = evaluator.initial_state
        for remove, add in [(1, 2), (0, 7), (3, 4), (2, 5), (7, 1)]:
            state = state.swap(remove, add)
            exact_counts, exact_z = evaluator.recompute(state.subset)
            self.assertEqual(state.z, exact_z)
            self.assertEqual({g: state.count(g) for g in group if state.count(g)},
                             exact_counts)
            self.assertEqual(state.z, len(group) - len(exact_counts))

    def test_noncommutative_group_and_parent_immutability(self):
        group = [(i, s) for i in range(4) for s in range(2)]
        evaluator = FiniteGroupProductDefect(
            group, self.d8_multiply, {(0, 0), (1, 0), (0, 1)}, compact_every=3
        )
        parent = evaluator.initial_state
        child = parent.swap((1, 0), (2, 1))
        self.assertEqual(parent.subset, frozenset({(0, 0), (1, 0), (0, 1)}))
        exact_counts, exact_z = evaluator.recompute(child.subset)
        self.assertEqual(child.z, exact_z)
        self.assertEqual(
            {g: child.count(g) for g in group if child.count(g)}, exact_counts
        )

    def test_swap_preconditions(self):
        evaluator = FiniteGroupProductDefect(range(4), lambda a, b: (a+b) % 4, {0, 1})
        with self.assertRaisesRegex(ValueError, "remove"):
            evaluator.initial_state.swap(2, 3)
        with self.assertRaisesRegex(ValueError, "add"):
            evaluator.initial_state.swap(0, 1)



    def test_lazy_swap_actions_cover_neighborhood_without_duplicates(self):
        group = range(8)
        evaluator = FiniteGroupProductDefect(
            group, lambda a, b: (a+b) % 8, {0, 1, 3}
        )
        problem = ProductDefectSearchProblem(evaluator, seed=23)
        state = evaluator.initial_state
        actions_a = list(problem.iter_actions(state))
        actions_b = list(problem.iter_actions(state))
        expected = {(remove, add) for remove in state.subset
                    for add in set(group) - state.subset}
        self.assertEqual(len(actions_a), len(expected))
        self.assertEqual(set(actions_a), expected)
        self.assertEqual(actions_a, actions_b)

    def test_lazy_product_defect_problem_runs_in_stream_mcts(self):
        group = range(8)
        evaluator = FiniteGroupProductDefect(
            group, lambda a, b: (a+b) % 8, {0, 1, 3}
        )
        problem = ProductDefectSearchProblem(evaluator, seed=7)
        _, root = mcts(
            problem, iterations=30, max_depth=4, max_nodes=20, seed=7,
            action_mode="stream", policy="uct",
            state_key=lambda state: state.subset,
        )
        self.assertGreater(root.stats["simulations"], 0)
        self.assertLessEqual(root.stats["created_nodes"], 20)
        self.assertTrue(root.children)


    def test_incremental_swap_uses_linear_group_multiplication_calls(self):
        calls = {"n": 0}
        def mul(a, b):
            calls["n"] += 1
            return (a + b) % 64

        subset = set(range(16))
        evaluator = FiniteGroupProductDefect(range(64), mul, subset)
        initial_calls = calls["n"]
        state = evaluator.initial_state.swap(3, 40)
        swap_calls = calls["n"] - initial_calls
        self.assertEqual(swap_calls, 4 * (len(subset) - 1) + 2)
        self.assertLess(swap_calls, len(subset) ** 2)
        exact_counts, exact_z = evaluator.recompute(state.subset)
        self.assertEqual(state.z, exact_z)
        self.assertEqual({g: state.count(g) for g in range(64) if state.count(g)},
                         exact_counts)


if __name__ == "__main__":
    unittest.main()
