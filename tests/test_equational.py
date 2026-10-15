"""Adversarial tests for the independent typed-equational logic layer.

No source identity is presumed mathematically true solely by the tests;
fixtures explicitly grant the reviewed axioms required for each derivation.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.equational import (
    Term, Equation, RewriteRule, EquationBook,
    prove_equation, verify_rewrite_certificate,
)
from math_mcts.logic_router import (
    load_equational_problem, solve_problem, certificate_data,
    load_rewrite_certificate, parse_term, term_data, verify_problem,
)


def C(x): return Term.const(x)
def V(x): return Term.var(x)
def F(name, *args): return Term.app(name, *args)


def group_like():
    # These are explicitly hypothetical caller-provided equations, not
    # certified algebra axioms or newly discovered identities.
    rules = [
        RewriteRule("unit_right", Equation(F("mul", V("?x"), C("e")), V("?x")),
                    (("?x", "S"),), "synthetic fixture", "reviewed"),
        RewriteRule("assoc", Equation(F("mul", F("mul", V("?x"), V("?y")), V("?z")),
                                      F("mul", V("?x"), F("mul", V("?y"), V("?z")))),
                    (("?x", "S"), ("?y", "S"), ("?z", "S")),
                    "synthetic fixture", "reviewed"),
        RewriteRule("unreviewed_magic", Equation(C("a"), C("z")),
                    (), "proposal only", "candidate"),
    ]
    return EquationBook(["S"], {"a":"S","b":"S","e":"S","z":"S"},
                        {"mul": (("S", "S"), "S"), "h": (("S",), "S")}, rules)


class EquationalTests(unittest.TestCase):
    def test_nested_congruence_and_source_verified_replay(self):
        book = group_like()
        original = F("h", F("mul", F("mul", C("a"), C("b")), C("e")))
        expected = F("h", F("mul", C("a"), C("b")))
        goal = Equation(original, expected)
        result = prove_equation(book, goal, max_steps=3)
        self.assertEqual(result.status, "proved_relative_to_equalities")
        self.assertTrue(result.certificate)
        self.assertTrue(verify_rewrite_certificate(book, result.certificate, goal))
        self.assertEqual(result.certificate.steps[0].position, (0,))
        self.assertEqual(result.depth, 1)

    def test_reverse_direction_is_checked(self):
        book = group_like()
        goal = Equation(C("a"), F("mul", C("a"), C("e")))
        result = prove_equation(book, goal, max_steps=2)
        self.assertTrue(result.certificate)
        self.assertTrue(result.certificate.steps[0].reverse)
        self.assertTrue(verify_rewrite_certificate(book, result.certificate, goal))

    def test_associativity_inside_context(self):
        book = group_like()
        goal = Equation(F("h", F("mul", F("mul", C("a"), C("b")), C("e"))),
                        F("h", F("mul", C("a"), F("mul", C("b"), C("e"))))
        result = prove_equation(book, goal, max_steps=1)
        self.assertEqual(result.depth, 1)
        self.assertTrue(verify_rewrite_certificate(book, result.certificate, goal))

    def test_ground_local_assumption_and_exact_scope(self):
        book = group_like()
        a = Equation(C("a"), C("b"))
        goal = Equation(F("h", C("a")), F("h", C("b")))
        self.assertIsNone(prove_equation(book, goal, max_steps=2).certificate)
        result = prove_equation(book, goal, assumptions=(a,), max_steps=2)
        self.assertTrue(result.certificate)
        self.assertEqual(result.certificate.steps[0].rule_id, "@assumption:0")
        self.assertFalse(verify_rewrite_certificate(book, result.certificate,
                                                    goal, assumptions=()))
        self.assertTrue(verify_rewrite_certificate(book, result.certificate,
                                                   goal, assumptions=(a,)))

    def test_candidate_and_refuted_cannot_execute(self):
        book = group_like()
        goal = Equation(C("a"), C("z"))
        result = prove_equation(book, goal, max_steps=4)
        self.assertIsNone(result.certificate)
        self.assertEqual(result.status, "not_found_within_budget")
        self.assertEqual(len(book.candidates), 1)

    def test_reflexivity_zero_steps_even_with_zero_budget(self):
        book = group_like()
        goal = Equation(F("h", C("a")), F("h", C("a")))
        result = prove_equation(book, goal, max_steps=0)
        self.assertEqual(result.depth, 0)
        self.assertEqual(result.certificate.steps, ())
        self.assertTrue(verify_rewrite_certificate(book, result.certificate, goal))

    def test_budget_miss_is_not_disproof(self):
        book = group_like()
        goal = Equation(F("h", F("mul", C("a"), C("e"))), F("h", C("a")))
        self.assertIsNone(prove_equation(book, goal, max_steps=0).certificate)
        self.assertTrue(prove_equation(book, goal, max_steps=1).certificate)
        with self.assertRaises(ValueError):
            prove_equation(book, goal, max_states=0)
        with self.assertRaises(ValueError):
            prove_equation(book, goal, max_term_nodes=0)

    def test_growth_and_state_budgets(self):
        growing = RewriteRule("growth", Equation(V("?x"), F("h", V("?x"))),
                              (("?x", "S"),), "synthetic", "reviewed")
        book = EquationBook(["S"], {"a":"S", "z":"S"}, {"h":(("S",),"S")}, [growing])
        goal = Equation(C("a"), C("z"))
        result = prove_equation(book, goal, max_steps=30,
                                max_states=4, max_term_nodes=4)
        self.assertIsNone(result.certificate)
        self.assertLessEqual(result.generated_states, 4)
        self.assertTrue(result.scope_exhausted)

    def test_wrong_sort_undeclared_symbol_and_arity(self):
        with self.assertRaises(ValueError):
            EquationBook(["S", "T"], {"a":"S","b":"T"}, {}, [
                RewriteRule("bad", Equation(C("a"), C("b")), (), "source", "reviewed")])
        book = group_like()
        for goal in (
            Equation(C("a"), C("missing")),
            Equation(F("mul", C("a")), C("a")),
            Equation(V("?x"), C("a")),
        ):
            with self.assertRaises(ValueError):
                prove_equation(book, goal)

    def test_unbound_witness_and_bad_variable_declarations(self):
        with self.assertRaisesRegex(ValueError, "same variables"):
            EquationBook(["S"], {"a":"S"}, {"h":(("S",),"S")}, [
                RewriteRule("invent", Equation(C("a"), V("?x")), (("?x", "S"),),
                            "source", "reviewed")])
        with self.assertRaisesRegex(ValueError, "invalid typed variables"):
            EquationBook(["S"], {"a":"S"}, {}, [
                RewriteRule("bad", Equation(C("a"), C("a")), (("?x", "NoSuchSort"),),
                            "source", "reviewed")])

    def test_repeated_variable_must_match(self):
        book = EquationBook(["S"], {"a":"S","b":"S"},
                            {"pair":(("S","S"),"S")},
                            [RewriteRule("idempotent",
                                Equation(F("pair", V("?x"), V("?x")), V("?x")),
                                (("?x","S"),), "synthetic", "reviewed")])
        self.assertTrue(prove_equation(book,
            Equation(F("pair", C("a"), C("a")), C("a"))).certificate)
        self.assertFalse(prove_equation(book,
            Equation(F("pair", C("a"), C("b")), C("a")),
            max_steps=1).certificate)

    def test_tampering_violations(self):
        book = group_like()
        goal = Equation(F("mul", C("a"), C("e")), C("a"))
        result = prove_equation(book, goal, max_steps=2)
        cert = result.certificate
        self.assertTrue(cert)
        original = cert.steps[0]
        variants = (
            replace(cert, goal=Equation(C("a"), C("a"))),
            replace(cert, rulebook_sha256="0" * 64),
            replace(cert, assumptions=(Equation(C("a"), C("z")),)),
            replace(cert, steps=(replace(original, rule_id="unreviewed_magic"),)),
            replace(cert, steps=(replace(original, position=(0, 0, 0)),)),
            replace(cert, steps=(replace(original, after=C("z")),)),
            replace(cert, steps=(replace(original, binding=(("?x", C("b")),)),)),
            replace(cert, steps=(replace(original, before=C("a")),)),
        )
        for invalid in variants:
            with self.subTest(invalid=invalid):
                self.assertFalse(verify_rewrite_certificate(book, invalid, goal))

    def test_rule_source_change_invalidates_old_proof(self):
        book = group_like()
        goal = Equation(F("mul", C("a"), C("e")), C("a"))
        cert = prove_equation(book, goal).certificate
        rows = [replace(r, source="changed") if r.id == "unit_right" else r
                for r in (*book.rules.values(), *book.candidates.values())]
        changed = EquationBook(book.sorts, book.constants, book.functions, rows)
        self.assertFalse(verify_rewrite_certificate(changed, cert, goal))

    def test_checked_candidate_provenance(self):
        with self.assertRaisesRegex(ValueError, "statement hash and review"):
            EquationBook(["S"], {"a":"S"}, {}, [
                RewriteRule("false_grade", Equation(C("a"), C("a")), (),
                            "source", "reviewed", "candidate-id", "", "")])

    def test_malformed_constructors_fail_closed(self):
        for data in ({"var":"?x","const":"x"}, {"app":"h"}, {"const":12}):
            with self.assertRaises(ValueError):
                parse_term(data)
        with self.assertRaises(ValueError):
            Term.app("h", "not a term")
        with self.assertRaises(ValueError):
            Term.var("x")


class MultiLogicRouterTests(unittest.TestCase):
    def fixture_data(self):
        def v(x): return {"var":x}
        def c(x): return {"const":x}
        def f(x,*args): return {"app":x,"args":list(args)}
        return {
            "logic":"equational",
            "signature":{"sorts":["S"],"constants":{"a":"S","e":"S"},
                         "functions":{"mul":{"args":["S","S"],"returns":"S"}}},
            "rules":[{"id":"right_unit","variables":{"?x":"S"},
                      "source":"explicit synthetic fixture","status":"reviewed",
                      "left": f("mul",v("?x"),c("e")), "right":v("?x")},
                     {"id":"candidate","variables":{},
                      "source":"untrusted","status":"candidate",
                      "left":c("a"),"right":c("e")}],
            "assumptions":[],
            "goal":{"left":f("mul",c("a"),c("e")),"right":c("a")}
        }

    def test_json_roundtrip_and_logic_router(self):
        data = self.fixture_data()
        book, assumptions, goal = load_equational_problem(data)
        report = solve_problem(data, max_steps=3)
        self.assertEqual(report["logic"],"equational")
        self.assertTrue(report["certificate_replayed"])
        self.assertEqual(report["reviewed_rules"],1)
        self.assertEqual(report["unverified_candidates"],1)
        payload = json.loads(json.dumps(report["certificate"]))
        cert = load_rewrite_certificate(payload)
        self.assertTrue(verify_rewrite_certificate(book, cert, goal, assumptions))
        self.assertEqual(term_data(goal.left),data["goal"]["left"])
        self.assertTrue(verify_problem(data, json.loads(json.dumps(report))))
        modified = copy.deepcopy(data)
        modified["rules"][0]["source"] += " altered"
        self.assertFalse(verify_problem(modified, report))

    def test_no_auto_logic_inference_or_candidate_promotion(self):
        data = self.fixture_data()
        without = copy.deepcopy(data)
        without.pop("logic")
        with self.assertRaises(ValueError):
            solve_problem(without)
        data["rules"][0]["status"] = "candidate"
        self.assertFalse(solve_problem(data)["certificate_replayed"])
        data["rules"][0]["status"] = "refuted"
        self.assertFalse(solve_problem(data)["certificate_replayed"])

    def test_json_tamper_replay_rejected(self):
        data = self.fixture_data()
        book, assumptions, goal = load_equational_problem(data)
        payload = solve_problem(data)["certificate"]
        payload["steps"][0]["binding"][0][1] = {"const":"e"}
        cert = load_rewrite_certificate(payload)
        self.assertFalse(verify_rewrite_certificate(book, cert, goal, assumptions))
        payload["steps"][0]["reverse"] = "false"
        with self.assertRaises(ValueError):
            load_rewrite_certificate(payload)

    def test_legacy_horn_dispatch_unchanged(self):
        from math_mcts.search_eval import mathematical_task_fixtures
        data = dict(mathematical_task_fixtures()["subset_transitivity"])
        data["logic"] = "horn"
        report = solve_problem(data, max_steps=5, iterations=10)
        self.assertEqual(report["logic"], "horn")
        self.assertTrue(report["certificate_replayed"])
        self.assertEqual(report["trust_scope"],
            "derivability_relative_to_caller_reviewed_ground_horn_rules")
        as_json = json.loads(json.dumps(report))
        self.assertTrue(verify_problem(data, as_json))
        modified = copy.deepcopy(data)
        modified["rules"][0]["source"] = "tampered"
        self.assertFalse(verify_problem(modified, as_json))


if __name__=="__main__":
    unittest.main()
