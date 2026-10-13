import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from examples.layered_collision import make_problem
from math_mcts.layered import (LayerConfig, CollisionLayer, derive_layers, replay_layers,
                              load_layered_problem, load_layer_certificate, report_json)


class LayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book, cls.facts, cls.goals, cls.cfg = load_layered_problem(make_problem())
        cls.result = derive_layers(cls.book, cls.facts, cls.goals, config=cls.cfg, iterations=2)

    def test_twenty_by_twenty_actual(self):
        metrics = self.result["metrics"]
        self.assertEqual(self.result["status"], "derived_relative_to_rules")
        self.assertEqual(metrics["effective_goal_depth"], 20)
        self.assertEqual(metrics["applied_rules"], 400)
        self.assertEqual(metrics["goal_relevant_rules"], 400)
        self.assertEqual(len(metrics["layers"]), 20)
        for row in metrics["layers"]:
            self.assertEqual(row["participating_knowledge"], 20)
            self.assertEqual(row["new_conclusions"], 20)
            self.assertEqual(row["goal_relevant_knowledge"], 20)

    def test_json_replay(self):
        data = json.loads(report_json(self.result))
        cert = load_layer_certificate(data["certificate"])
        self.assertEqual(replay_layers(self.book, cert, self.facts, self.goals, self.cfg),
                         self.result["metrics"])

    def test_missing_premise_cannot_pad(self):
        result = derive_layers(self.book, frozenset(sorted(self.facts)[:-1]), self.goals,
                               config=self.cfg, iterations=2)
        self.assertIsNone(result["certificate"])
        self.assertEqual(result["max_layers_reached"], 0)
        self.assertTrue(result["shortages"])

    def test_config_rejects_under_twenty(self):
        for kwargs in ({"min_knowledge": 19}, {"min_layers": 19}, {"max_layers": 19},
                       {"batch_width": 0}, {"batch_choices": True}):
            with self.assertRaises(ValueError):
                LayerConfig(**kwargs)

    def test_early_goal_cannot_pad_depth(self):
        goal = self.book.rules["layer_001_rule_000"].conclusion
        result = derive_layers(self.book, self.facts, [goal], config=self.cfg, iterations=2)
        self.assertIsNone(result["certificate"])

    def test_same_layer_dependency_rejected(self):
        cert = self.result["certificate"]
        # Combining two successive rounds must not hide intra-round inference.
        cfg = replace(self.cfg, batch_width=40)
        merged = CollisionLayer(cert.layers[0].edges + cert.layers[1].edges)
        layers = (merged,) + cert.layers[2:] + (cert.layers[-1],)
        fake = replace(cert, layers=layers, config=cfg)
        self.assertIsNone(replay_layers(self.book, fake, self.facts, self.goals, cfg))

    def test_duplicate_edges_and_assumption_forgery(self):
        cert = self.result["certificate"]
        layer = cert.layers[0]
        fake = replace(cert, layers=(CollisionLayer((layer.edges[0],) * 20),) + cert.layers[1:])
        self.assertIsNone(replay_layers(self.book, fake, self.facts, self.goals, self.cfg))
        self.assertIsNone(replay_layers(self.book, replace(cert, assumptions=self.facts | {self.goals[0]}),
                                       self.facts, self.goals, self.cfg))

    def test_budget_truncation_reported(self):
        cfg = replace(self.cfg, batch_width=1, max_candidates=1)
        result = derive_layers(self.book, self.facts, self.goals, config=cfg, iterations=2)
        self.assertTrue(result["candidate_truncated"])
        self.assertIsNone(result["certificate"])
        self.assertFalse(result["search_complete"])

    def test_beyond_twenty(self):
        book, facts, goals, cfg = load_layered_problem(make_problem(21, 21))
        result = derive_layers(book, facts, goals, config=cfg, iterations=1)
        self.assertEqual(result["metrics"]["effective_goal_depth"], 21)
        self.assertEqual(result["metrics"]["applied_rules"], 441)

    def test_twenty_inputs_one_output_each_layer(self):
        from math_mcts import Atom, Rule, RuleBook
        anchors = [Atom(f"anchor{i}") for i in range(19)]
        chain = [Atom(f"chain{i}") for i in range(21)]
        rules = [Rule(f"r{i}", tuple(anchors + [chain[i]]), chain[i+1],
                      source="synthetic", status="reviewed") for i in range(20)]
        book = RuleBook({a.predicate: () for a in anchors + chain}, {}, rules)
        result = derive_layers(book, anchors + chain[:1], chain[-1:], iterations=1)
        self.assertEqual(result["metrics"]["effective_goal_depth"], 20)
        self.assertEqual(result["metrics"]["applied_rules"], 20)
        self.assertTrue(all(r["goal_relevant_knowledge"] == 20
                            for r in result["metrics"]["layers"]))

    def test_unrelated_edges_cannot_pad_goal_knowledge(self):
        data = make_problem()
        for rule in data["rules"]:
            j = int(rule["id"].split("_")[-1])
            rule["premises"] = [rule["premises"][j]]
        data["goals"] = data["goals"][:1]
        book, facts, goals, cfg = load_layered_problem(data)
        result = derive_layers(book, facts, goals, config=cfg, iterations=1)
        self.assertIsNone(result["certificate"])

    def test_repeated_premises_do_not_count_twenty(self):
        data = make_problem()
        for rule in data["rules"]:
            rule["premises"] = [rule["premises"][0]] * 20
        book, facts, goals, cfg = load_layered_problem(data)
        result = derive_layers(book, facts, goals, config=cfg, iterations=1)
        self.assertIsNone(result["certificate"])
        self.assertEqual(result["shortages"][0]["available_knowledge"], 1)


if __name__ == "__main__":
    unittest.main()
