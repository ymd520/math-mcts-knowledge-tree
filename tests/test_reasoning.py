"""Adversarial tests for the trusted boundary and actual dependency depth."""
import sys
import unittest
import json
import random
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from math_mcts.reasoning import (Atom, Rule, RuleBook, Certificate, ProofGraph,
    DiscoveryQueue, DerivationProblem, derive, verify_certificate, load_certificate,
    load_reasoning_problem)


def fixture():
    signatures = {"compact": ("Space",), "nonempty": ("Space",),
                  "continuous": ("Map", "Space"), "image": ("Map", "Space", "Set"),
                  "compact_set": ("Set",), "nonempty_set": ("Set",),
                  "real_set": ("Set",), "extrema": ("Set",), "attains": ("Map", "Space")}
    objects = {"X": "Space", "Y": "Space", "f": "Map", "I": "Set", "J": "Set"}
    a = Atom
    rules = [
        Rule("compact_image", (a("compact", ("?x",)), a("continuous", ("?f", "?x")),
             a("image", ("?f", "?x", "?i"))), a("compact_set", ("?i",)),
             (("?x", "Space"), ("?f", "Map"), ("?i", "Set")), "REASONING.md#rules", "reviewed"),
        Rule("nonempty_image", (a("nonempty", ("?x",)), a("image", ("?f", "?x", "?i"))),
             a("nonempty_set", ("?i",)), (("?x", "Space"), ("?f", "Map"), ("?i", "Set")),
             "REASONING.md#rules", "reviewed"),
        Rule("compact_real_extrema", (a("compact_set", ("?i",)), a("nonempty_set", ("?i",)),
             a("real_set", ("?i",))), a("extrema", ("?i",)), (("?i", "Set"),),
             "REASONING.md#rules", "reviewed"),
        Rule("attainment", (a("extrema", ("?i",)), a("image", ("?f", "?x", "?i"))),
             a("attains", ("?f", "?x")), (("?x", "Space"), ("?f", "Map"), ("?i", "Set")),
             "REASONING.md#rules", "reviewed")]
    facts = frozenset([a("compact", ("X",)), a("nonempty", ("X",)),
                     a("continuous", ("f", "X")), a("image", ("f", "X", "I")),
                     a("real_set", ("I",))])
    return RuleBook(signatures, objects, rules), facts, a("attains", ("f", "X"))


class ReasoningTests(unittest.TestCase):
    def test_multibranch_certificate(self):
        book, facts, goal = fixture()
        for seed in (1, 7, 19):
            result = derive(book, facts, goal, iterations=80, seed=seed)
            self.assertEqual(result.status, "derived_relative_to_rules")
            self.assertEqual(result.applied_rules, 4)
            self.assertEqual(result.effective_depth, 3)
            self.assertTrue(verify_certificate(book, result.certificate, facts, goal))

    def test_missing_each_assumption(self):
        book, facts, goal = fixture()
        for fact in facts:
            result = derive(book, facts - {fact}, goal, iterations=40)
            self.assertIsNone(result.certificate, fact)

    def test_same_predicate_different_object(self):
        book, facts, goal = fixture()
        facts = facts - {Atom("nonempty", ("X",))} | {Atom("nonempty", ("Y",))}
        self.assertIsNone(derive(book, facts, goal, iterations=30).certificate)

    def test_wrong_type_and_arity(self):
        book, facts, goal = fixture()
        for bad in (Atom("compact", ("f",)), Atom("compact", ()), Atom("unknown")):
            with self.assertRaises(ValueError):
                derive(book, facts | {bad}, goal)

    def test_candidate_and_refuted_rules_excluded(self):
        book, facts, goal = fixture()
        for status in ("candidate", "refuted"):
            fake = Rule("fake", (), goal, source="proposal", status=status)
            b = RuleBook(book.signatures, book.objects, [fake])
            self.assertIsNone(derive(b, facts, goal, iterations=5).certificate)

    def test_no_implicit_witness(self):
        with self.assertRaises(ValueError):
            RuleBook({"p": ("T",), "q": ("T",)}, {"a": "T"}, [
                Rule("invent", (Atom("p", ("a",)),), Atom("q", ("?x",)),
                     (("?x", "T"),), "test", "reviewed")])

    def test_tamper_certificate(self):
        book, facts, goal = fixture()
        cert = derive(book, facts, goal, iterations=30).certificate
        forged = replace(cert.steps[0], conclusion=goal)
        self.assertFalse(verify_certificate(book, replace(cert, steps=(forged,)), facts, goal))
        self.assertFalse(verify_certificate(book, replace(cert, assumptions=facts | {goal}), facts, goal))
        self.assertFalse(verify_certificate(book, replace(cert, steps=cert.steps[::-1]), facts, goal))
        self.assertFalse(verify_certificate(book, cert, facts, Atom("extrema", ("I",))))

    def test_changed_rule_invalidates_certificate(self):
        book, facts, goal = fixture()
        cert = derive(book, facts, goal, iterations=30).certificate
        rules = [replace(r, status="candidate") for r in book.rules.values()]
        changed = RuleBook(book.signatures, book.objects, rules)
        self.assertFalse(verify_certificate(changed, cert, facts, goal))

    def test_budget_is_not_disproof(self):
        book, facts, goal = fixture()
        result = derive(book, facts, goal, iterations=5, max_steps=2, max_edges=1)
        self.assertEqual(result.status, "not_found_within_budget")
        self.assertFalse(result.scope_complete)
        self.assertEqual(result.scope_reason, "edge_budget")

    def test_already_assumed_goal(self):
        book, facts, goal = fixture()
        result = derive(book, facts | {goal}, goal, iterations=1)
        self.assertEqual(result.effective_depth, 0)
        self.assertEqual(result.certificate.steps, ())

    def test_cycle_does_not_bootstrap_itself(self):
        a = Atom("a", ("x",)); b = Atom("b", ("x",))
        book = RuleBook({"a": ("T",), "b": ("T",)}, {"x": "T"}, [
            Rule("ab", (a,), b, source="test", status="reviewed"),
            Rule("ba", (b,), a, source="test", status="reviewed")])
        self.assertIsNone(derive(book, [], b, iterations=5).certificate)
        self.assertTrue(derive(book, [a], b, iterations=5).certificate)

    def test_repeated_variable(self):
        book = RuleBook({"rel": ("T", "T"), "diag": ("T",)}, {"a": "T", "b": "T"}, [
            Rule("diag", (Atom("rel", ("?x", "?x")),), Atom("diag", ("?x",)),
                 (("?x", "T"),), "test", "reviewed")])
        self.assertIsNone(derive(book, [Atom("rel", ("a", "b"))], Atom("diag", ("a",)), iterations=5).certificate)

    def test_real_20_layer_chain(self):
        atoms = [Atom(f"p{i}", ("x",)) for i in range(21)]
        book = RuleBook({a.predicate: ("T",) for a in atoms}, {"x": "T"}, [
            Rule(f"r{i}", (atoms[i],), atoms[i+1], source="synthetic test", status="reviewed")
            for i in range(20)])
        result = derive(book, atoms[:1], atoms[-1], iterations=2, max_steps=20)
        self.assertEqual(result.effective_depth, 20)
        self.assertEqual(result.applied_rules, 20)
        self.assertIsNone(derive(book, atoms[:1], atoms[-1], iterations=2, max_steps=19).certificate)

    def test_fact_state_cache_and_disabled_action(self):
        book, facts, goal = fixture()
        graph = ProofGraph.build(book, facts, goal)
        p = DerivationProblem(graph, facts, goal, 10)
        state = p.initial_state()
        a, b = p.actions(state)
        ab = p.step(p.step(state, a), b)
        ba = p.step(p.step(state, b), a)
        self.assertEqual(ab.facts, ba.facts)
        self.assertEqual(p.actions(ab), p.actions(ba))
        with self.assertRaises(ValueError):
            p.step(state, next(e for e in graph.edges if e.rule_id == "attainment"))

    def test_proposals_remain_unverified(self):
        q = DiscoveryQueue()
        q.propose("conjecture", source_ids=("K1",), falsification="find counterexample")
        self.assertEqual(q.proposals[0]["status"], "unverified")

    def test_exhaustive_boolean_fixture(self):
        # Necessary and sufficient assumptions of this explicit four-rule fixture.
        book, facts, goal = fixture()
        facts = sorted(facts)
        for mask in range(1 << len(facts)):
            initial = frozenset(f for i, f in enumerate(facts) if mask & (1 << i))
            result = derive(book, initial, goal, iterations=20)
            self.assertEqual(result.certificate is not None, mask == 31)

    def test_random_horn_against_independent_closure(self):
        rng = random.Random(28)
        atoms = [Atom(f"p{i}") for i in range(6)]
        for case in range(30):
            rules = []
            raw = []
            for i in range(10):
                premises = tuple(rng.sample(atoms, rng.randrange(4)))
                conclusion = rng.choice(atoms)
                raw.append((set(premises), conclusion))
                rules.append(Rule(str(i), premises, conclusion, source="synthetic", status="reviewed"))
            initial = frozenset(rng.sample(atoms, 2))
            goal = rng.choice(atoms)
            closure = set(initial)
            while True:
                updated = closure | {c for p, c in raw if p <= closure}
                if updated == closure:
                    break
                closure = updated
            book = RuleBook({a.predicate: () for a in atoms}, {}, rules)
            result = derive(book, initial, goal, iterations=200, max_steps=6)
            self.assertEqual(result.certificate is not None, goal in closure, case)

    def test_json_roundtrip_and_provenance_binding(self):
        data = json.loads(Path(__file__).resolve().parent.parent.joinpath(
            "examples/extreme_value.json").read_text())
        book, facts, goal = load_reasoning_problem(data)
        cert = derive(book, facts, goal, iterations=30).certificate
        from dataclasses import asdict
        def default(value):
            return [asdict(a) for a in sorted(value)]
        loaded = load_certificate(json.loads(json.dumps(asdict(cert), default=default)))
        self.assertTrue(verify_certificate(book, loaded, facts, goal))
        changed = RuleBook(book.signatures, book.objects,
                           [replace(r, source=r.source + "#changed") for r in book.rules.values()])
        self.assertFalse(verify_certificate(changed, loaded, facts, goal))

    def test_actual_knowledge_adapter_stays_untrusted(self):
        from math_mcts import KnowledgeTree
        tree = KnowledgeTree.load()
        selected = KnowledgeTree(tree.concepts[:3])
        q = DiscoveryQueue()
        q.ingest_concepts(selected)
        self.assertEqual(len(q.proposals), 3)
        self.assertEqual(q.proposals[0]["source_ids"], [selected.concepts[0].id])
        self.assertTrue(all(p["status"] == "unverified" for p in q.proposals))


if __name__ == "__main__":
    unittest.main()
