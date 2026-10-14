"""Actual set-theoretic inference, not synthetic stipulated rule chain."""
from __future__ import annotations
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from examples.set_membership_20x20 import make_set_transport,run_set_transport
from math_mcts.layered import replay_layers,CollisionLayer
from math_mcts.reasoning import Hyperedge


class SetTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book,cls.assumptions,cls.goals,cls.config=make_set_transport()
        cls.result=run_set_transport(iterations=2)

    def test_genuine_valid_inclusion_schema_has_20x20_goal_relevance(self):
        result=self.result
        self.assertEqual(result["status"],"derived_relative_to_rules",result)
        m=result["metrics"]
        self.assertEqual(m["effective_goal_depth"],20)
        self.assertEqual(m["applied_rules"],400)
        self.assertEqual(len(m["layers"]),20)
        self.assertEqual(m["goal_relevant_rules"],400)
        for row in m["layers"]:
            self.assertEqual(row["new_conclusions"],20)
            self.assertEqual(row["goal_relevant_rules"],20)
            self.assertGreaterEqual(row["goal_relevant_knowledge"],20)
            self.assertGreaterEqual(row["previous_frontier_inputs"],20)
        self.assertIsNotNone(replay_layers(
            self.book,result["certificate"],self.assumptions,self.goals,self.config))
        self.assertTrue(result["generated_instance_not_research_theorem"])

    def test_broken_set_inclusion_never_forged_as_proven(self):
        result=run_set_transport(iterations=2,omit_subset_at=9)
        self.assertIsNone(result["certificate"])
        self.assertIsNone(result["metrics"])
        self.assertEqual(result["status"],"not_found_within_budget")

    def test_tampered_membership_proof_not_replayable(self):
        cert=self.result["certificate"]
        first=cert.layers[0]
        wrong=replace(first.edges[0],rule_id="not_a_mathematical_rule")
        bad=replace(cert,layers=(CollisionLayer((wrong,)+first.edges[1:]),)+cert.layers[1:])
        self.assertIsNone(replay_layers(
            self.book,bad,self.assumptions,self.goals,self.config))


if __name__=="__main__":
    unittest.main()
