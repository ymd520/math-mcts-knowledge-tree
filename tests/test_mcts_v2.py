"""Independent adversarial tests for goal-guided tree search and Horn closure."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
import math
from pathlib import Path
import json
import sqlite3
import tempfile
import random
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.mcts import Problem, mcts
from math_mcts.reasoning import Atom, Hyperedge, Rule, RuleBook, ProofGraph, derive, verify_certificate
from math_mcts.hypergraph_closure import forward_certificate
from math_mcts.source_expansion import import_jsonl
from math_mcts.candidate_rule_bridge import candidate_rules, bridge_report


def atom(name):
    return Atom(name)


def closure_book(edges, candidates=()):
    atoms = {s for p, q in edges for s in (*p, q)}
    rules = [Rule(f"r{i}", tuple(p), q, source="explicit reviewed fixture", status="reviewed")
             for i, (p, q) in enumerate(edges)]
    rules.extend(candidates)
    return RuleBook({x.predicate: () for x in atoms}, {}, rules)


def independent_least_fixed_point(edges, initial):
    facts = set(initial)
    while True:
        updated = facts | {q for premises, q in edges if set(premises) <= facts}
        if updated == facts:
            return facts
        facts = updated


class ClosureTests(unittest.TestCase):
    def test_diamond_shared_premises_one_copy(self):
        a, b, c, d, e = map(atom, "abcde")
        rules = [((a,), b), ((a,), c), ((b, c), d), ((d,), e)]
        book = closure_book(rules)
        graph = ProofGraph.build(book, frozenset([a]), e)
        found = forward_certificate(book, graph, frozenset([a]), e, max_steps=4)
        self.assertTrue(found.reached)
        self.assertEqual(found.proof_steps, 4)
        self.assertEqual(found.effective_depth, 3)
        self.assertTrue(verify_certificate(book, found.certificate, frozenset([a]), e))
        self.assertEqual(derive(book, [a], e, iterations=1).search_method, "event_driven_closure")

    def test_missing_premise_and_candidate_rule_cannot_help(self):
        a, b, c = map(atom, "abc")
        fake = Rule("fake", (b,), c, source="unverified", status="candidate")
        book = closure_book([((a, b), c)], [fake])
        graph = ProofGraph.build(book, frozenset([a]), c)
        report = forward_certificate(book, graph, frozenset([a]), c)
        self.assertFalse(report.reached)
        self.assertIsNone(report.certificate)
        self.assertEqual(derive(book, [a], c, iterations=5).status,
                         "not_derivable_from_reviewed_ground_rules")

    def test_chain_over_budget_not_returned(self):
        xs = [atom(f"x{i}") for i in range(30)]
        book = closure_book([((xs[i],), xs[i+1]) for i in range(29)])
        graph = ProofGraph.build(book, frozenset([xs[0]]), xs[-1])
        result = forward_certificate(book, graph, frozenset([xs[0]]), xs[-1],
                                     max_steps=28)
        self.assertTrue(result.reached)
        self.assertTrue(result.witness_over_budget)
        self.assertIsNone(result.certificate)
        self.assertEqual(result.proof_steps, 29)
        r = derive(book, [xs[0]], xs[-1], max_steps=28, iterations=2)
        self.assertIsNone(r.certificate)
        self.assertNotEqual(r.status, "derived_relative_to_rules")

    def test_cycle_cannot_self_prove(self):
        a, b = atom("a"), atom("b")
        book = closure_book([((a,), b), ((b,), a)])
        graph = ProofGraph.build(book, frozenset(), b)
        self.assertFalse(forward_certificate(book, graph, frozenset(), b).reached)

    def test_forged_graph_edge_cannot_enter_certificates(self):
        a, b = atom("a"), atom("b")
        book = closure_book([((a,), b)])
        fake = Hyperedge("r0", (), (a,), a)
        with self.assertRaises(ValueError):
            forward_certificate(book, ProofGraph((fake,), False, "truncated"),
                                frozenset([a]), b)

    def test_graph_incomplete_no_disproof_claim(self):
        a, b, c = map(atom, "abc")
        book = closure_book([((a,), b), ((b,), c)])
        graph = ProofGraph.build(book, frozenset([a]), c, max_edges=1)
        report = forward_certificate(book, graph, frozenset([a]), c)
        self.assertFalse(graph.complete)
        self.assertEqual(report.status, "not_found_in_truncated_graph")
        result = derive(book, [a], c, iterations=2, max_edges=1)
        self.assertFalse(result.scope_complete)
        self.assertIsNone(result.certificate)

    def test_independent_randomized_closure_and_certificate_replay(self):
        rng = random.Random(20261015)
        facts = [atom(f"f{i}") for i in range(9)]
        for _ in range(60):
            edges = [(tuple(rng.sample(facts, rng.randrange(4))), rng.choice(facts))
                     for _ in range(30)]
            book = closure_book(edges)
            initial = frozenset(rng.sample(facts, 2))
            goal = rng.choice(facts)
            graph = ProofGraph.build(book, initial, goal, max_rounds=50, max_edges=500)
            report = forward_certificate(book, graph, initial, goal)
            self.assertEqual(report.reached, goal in independent_least_fixed_point(edges, initial))
            self.assertTrue(graph.complete)
            if report.certificate:
                self.assertTrue(verify_certificate(book, report.certificate, initial, goal))

    def test_long_chain_no_recursion_error(self):
        n = 1100
        xs = [atom(f"z{i}") for i in range(n + 1)]
        book = closure_book([((xs[i],), xs[i+1]) for i in range(n)])
        # Construct ground edges with genuine exact instantiation, bypassing
        # ProofGraph.build's default 100-round cutoff for this stress test.
        ground = tuple(book.instantiate(f"r{i}", {}) for i in range(n))
        report = forward_certificate(book, ProofGraph(ground, True, "fixed_point"),
                                     frozenset([xs[0]]), xs[-1], max_steps=n)
        self.assertEqual(report.proof_steps, n)
        self.assertTrue(report.certificate is not None)


class GuidedMCTSTests(unittest.TestCase):
    class Toy(Problem):
        def __init__(self):
            self.reached = False
        def initial_state(self):
            return "start"
        def actions(self, state):
            return list(range(200)) if state == "start" else []
        def step(self, state, action):
            return action
        def terminal(self, state):
            return state != "start"
        def reward(self, state):
            if state == 199:
                self.reached = True
                return 1.0
            return 0.0
        def success_found(self):
            return self.reached
        def action_weight(self, state, action):
            return 1000.0 if action == 199 else 0.1

    def test_guided_stop_and_reproducible_search(self):
        p = self.Toy()
        sequence, root = mcts(p, iterations=200, seed=11, policy="puct",
                              stop_on_success=True)
        self.assertEqual(sequence, [199])
        self.assertTrue(root.stats["early_stop"])
        self.assertLess(root.stats["simulations"], 200)
        self.assertEqual(root.stats["created_nodes"], 2)
        q = self.Toy()
        sequence2, root2 = mcts(q, iterations=200, seed=11, policy="puct",
                                 stop_on_success=True)
        self.assertEqual(sequence2, sequence)
        self.assertEqual(root2.stats, root.stats)

    def test_default_uct_backward_compatible(self):
        _, root = mcts(self.Toy(), iterations=10, seed=7)
        self.assertEqual(root.stats["policy"], "uct")
        self.assertEqual(root.stats["simulations"], 10)
        self.assertEqual(root.stats["guided_expansions"], 0)

    def test_invalid_policy_or_prior_rejected(self):
        with self.assertRaises(ValueError):
            mcts(self.Toy(), iterations=1, policy="unknown")
        class Wrong(self.Toy):
            def action_weight(self, state, action):
                return math.nan
        with self.assertRaises(ValueError):
            mcts(Wrong(), iterations=1, policy="puct")

    def test_zero_priors_fall_back_to_uniform(self):
        class Zero(self.Toy):
            def action_weight(self, state, action):
                return 0.0
        _, root = mcts(Zero(), iterations=3, policy="puct", seed=4)
        self.assertEqual(root.stats["simulations"], 3)


class CandidateRuleBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "external.sqlite"
        p = self.root / "records.jsonl"
        p.write_text(json.dumps({
            "source": "example-project", "source_ref": "version-2026-verified-by-curator",
            "source_url": "https://example.org/source", "license": "review-required",
            "locator": "Analysis.some_theorem", "name": "Some theorem",
            "kind": "theorem", "statement": "If P(x) holds, then Q(x) holds."
        }) + "\\n", encoding="utf-8")
        import_jsonl(self.db, p)
        with sqlite3.connect(self.db) as db:
            self.entry = json.loads(db.execute(
                "SELECT record FROM external_candidates").fetchone()[0])
        self.spec = {"candidates": [self.mapping()],
                     "signatures": {"P": ["T"], "Q": ["T"]},
                     "objects": {"a": "T"}}

    def mapping(self):
        return {
            "candidate_id": self.entry["id"],
            "statement_sha256": self.entry["statement_sha256"],
            "variables": {"?x": "T"},
            "premises": [{"predicate": "P", "args": ["?x"]}],
            "conclusion": {"predicate": "Q", "args": ["?x"]},
            "status": "candidate"
        }

    def test_typed_translation_is_not_executable(self):
        rules = candidate_rules(self.db, self.spec["candidates"],
                                self.spec["signatures"], self.spec["objects"])
        self.assertEqual(len(rules), 1)
        book = RuleBook(self.spec["signatures"], self.spec["objects"], list(rules))
        self.assertFalse(book.rules)
        self.assertEqual(len(book.candidates), 1)
        self.assertIsNone(derive(book, [Atom("P", ("a",))],
                                 Atom("Q", ("a",)), iterations=2).certificate)
        path = self.root / "mapping.json"
        path.write_text(json.dumps(self.spec), encoding="utf-8")
        report = bridge_report(self.db, path)
        self.assertEqual(report["active_reviewed_rules"], 0)
        self.assertFalse(report["semantic_translation_verified"])

    def test_reject_fake_proof_grade_and_bad_type(self):
        m = self.mapping()
        m["status"] = "reviewed"
        with self.assertRaisesRegex(ValueError, "self-promote"):
            candidate_rules(self.db, [m], self.spec["signatures"], self.spec["objects"])
        m = self.mapping()
        m["statement_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            candidate_rules(self.db, [m], self.spec["signatures"], self.spec["objects"])
        m = self.mapping()
        m["conclusion"] = {"predicate": "Q", "args": ["a", "a"]}
        with self.assertRaises(ValueError):
            candidate_rules(self.db, [m], self.spec["signatures"], self.spec["objects"])
        m = self.mapping()
        m["premises"] = []
        with self.assertRaises(ValueError):
            candidate_rules(self.db, [m], self.spec["signatures"], self.spec["objects"])

    def test_duplicate_mapping_rejected(self):
        m = self.mapping()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            candidate_rules(self.db, [m, m], self.spec["signatures"], self.spec["objects"])


if __name__ == "__main__":
    unittest.main()
