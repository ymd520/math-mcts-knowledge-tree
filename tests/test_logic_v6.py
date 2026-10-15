"""Adversarial finite quantifiers, conditional rewriting and source trust tests.

Finite enumeration is checked ONLY over explicitly declared constants. These
fixtures use synthetic axioms, never claims of new mathematical discoveries.
"""
from __future__ import annotations
from dataclasses import replace
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.equational import Equation, EquationBook, RewriteRule, Term, prove_equation
from math_mcts.finite_logic import (Formula, FiniteProof, instantiate_formula,
                                    prove_finite, verify_finite_certificate,
                                    validate_formula)
from math_mcts.conditional_logic import (ConditionalRule, ConditionalBook,
                                         prove_guarded, verify_guarded_certificate)
from math_mcts.logic_router import solve_problem, verify_problem


def c(name): return Term.const(name)
def v(name): return Term.var(name)
def f(name,*args): return Term.app(name,*args)
def eq(left,right): return Equation(left,right)


def base_book(include_unit=True):
    rules = ([RewriteRule("unit", eq(f("mul",v("?x"),c("e")),v("?x")),
                          (("?x","S"),), "fixture reviewed rule", "reviewed")]
             if include_unit else [])
    rules += [RewriteRule("untrusted",eq(c("a"),c("z")),(),
                          "fixture unreviewed", "candidate")]
    return EquationBook(
        ["S","T"], {"a":"S","b":"S","e":"S","z":"S","t":"T"},
        {"mul":(("S","S"),"S"), "h":(("S",),"S"),"mark":(("S",),"S"),
         "f":(("S",),"S"),"g":(("S",),"S"),"bad":(("S",),"S")},
        rules)


class FiniteQuantifierTests(unittest.TestCase):
    def test_universal_expands_every_declared_element(self):
        book = base_book()
        statement = Formula.forall("?x","S",
            Formula.eqn(eq(f("mul",v("?x"),c("e")),v("?x"))))
        result=prove_finite(book,statement,max_steps=2)
        self.assertTrue(result.certificate,result)
        self.assertEqual(result.instantiated_quantifier_cases,4)
        self.assertEqual(len(result.certificate.proof.leaves),4)
        self.assertTrue(verify_finite_certificate(book,result.certificate,statement))

    def test_missing_universal_instance_must_reject(self):
        book=base_book()
        formula=Formula.forall("?x","S",
            Formula.eqn(eq(f("mul",v("?x"),c("e")),v("?x"))))
        cert=prove_finite(book,formula).certificate
        invalid=replace(cert,proof=replace(cert.proof,leaves=cert.proof.leaves[:-1]))
        self.assertFalse(verify_finite_certificate(book,invalid,formula))
        # Explicit universe change invalidates both proof digest and totality.
        altered=EquationBook(["S","T"],{**book.constants,"extra":"S"},book.functions,
                             list(book.rules.values())+list(book.candidates.values()))
        self.assertFalse(verify_finite_certificate(altered,cert,formula))

    def test_existential_only_accepts_concrete_declared_witness(self):
        book=base_book()
        formula=Formula.exists("?x","S",
            Formula.eqn(eq(f("mul",v("?x"),c("e")),v("?x"))))
        proof=prove_finite(book,formula,max_steps=1).certificate
        self.assertEqual(proof.proof.witness,"a")
        self.assertTrue(verify_finite_certificate(book,proof,formula))
        self.assertFalse(verify_finite_certificate(book,replace(
            proof,proof=replace(proof.proof,witness="nonexistent")),formula))
        self.assertFalse(verify_finite_certificate(book,replace(
            proof,proof=replace(proof.proof,witness="t")),formula))

    def test_implication_adds_only_its_explicit_equality_hypotheses(self):
        book=base_book(include_unit=False)
        formula=Formula.forall("?x","S",
            Formula.implies((eq(v("?x"),c("a")),),
              Formula.eqn(eq(f("h",v("?x")),f("h",c("a"))))))
        result=prove_finite(book,formula,max_steps=2)
        self.assertTrue(result.certificate,result)
        self.assertTrue(verify_finite_certificate(book,result.certificate,formula))
        without=Formula.forall("?x","S",
            Formula.eqn(eq(f("h",v("?x")),f("h",c("a")))))
        self.assertIsNone(prove_finite(book,without,max_steps=2).certificate)
        # Bound proof leaf cannot silently discard its assumption.
        leaf=result.certificate.proof.leaves[1].leaves[0].equality
        fake=replace(leaf,assumptions=())
        inner=result.certificate.proof.leaves[1]
        altered=replace(inner,leaves=(replace(inner.leaves[0],equality=fake),))
        children=list(result.certificate.proof.leaves)
        children[1]=altered
        cert=replace(result.certificate,proof=replace(
            result.certificate.proof,leaves=tuple(children)))
        self.assertFalse(verify_finite_certificate(book,cert,formula))

    def test_nested_conjunction_disjunction_and_wrong_case(self):
        book=base_book()
        true=Formula.eqn(eq(f("mul",c("b"),c("e")),c("b")))
        false=Formula.eqn(eq(c("a"),c("z")))
        formula=Formula.conj(Formula.disj(false,true),true)
        proof=prove_finite(book,formula,max_steps=2).certificate
        self.assertTrue(proof)
        self.assertEqual(proof.proof.leaves[0].witness,"1")
        self.assertTrue(verify_finite_certificate(book,proof,formula))
        forged=replace(proof,proof=replace(proof.proof,
            leaves=(replace(proof.proof.leaves[0],witness="0"),proof.proof.leaves[1])))
        self.assertFalse(verify_finite_certificate(book,forged,formula))

    def test_empty_domain_vacuous_forall_not_exists(self):
        book=EquationBook(["Void","S"],{"a":"S"},{},[])
        yes=Formula.forall("?x","Void",Formula.eqn(eq(v("?x"),v("?x"))))
        no=Formula.exists("?x","Void",Formula.eqn(eq(v("?x"),v("?x"))))
        self.assertIsNotNone(prove_finite(book,yes).certificate)
        self.assertIsNone(prove_finite(book,no).certificate)

    def test_binder_capture_sort_and_free_variables_fail_closed(self):
        book=base_book()
        shadow=Formula.forall("?x","S",Formula.exists("?x","S",
            Formula.eqn(eq(v("?x"),v("?x")))))
        wrongsort=Formula.forall("?x","T",
            Formula.eqn(eq(f("h",v("?x")),v("?x"))))
        free=Formula.eqn(eq(v("?x"),v("?x")))
        for formula in (shadow,wrongsort,free):
            with self.subTest(formula=formula), self.assertRaises(ValueError):
                validate_formula(book,formula)
        with self.assertRaises(ValueError):
            Formula.conj()

    def test_hard_instance_and_tree_budgets_cannot_claim_proof(self):
        book=base_book()
        stmt=Formula.forall("?x","S",Formula.eqn(eq(v("?x"),v("?x"))))
        self.assertIsNone(prove_finite(book,stmt,max_cases=1).certificate)
        self.assertIsNone(prove_finite(book,stmt,max_nodes=2).certificate)

    def test_candidate_lemma_not_implicitly_enabled(self):
        book=base_book()
        fmla=Formula.exists("?x","S",Formula.eqn(eq(c("a"),c("z"))))
        self.assertIsNone(prove_finite(book,fmla,max_steps=2).certificate)


class GuardedRewriteTests(unittest.TestCase):
    def fixture(self):
        base=base_book(include_unit=False)
        unconditional=RewriteRule("known",eq(f("mark",c("a")),c("e")),
                                  (), "explicit trusted fixture", "reviewed")
        base=EquationBook(base.sorts,base.constants,base.functions,
                          list(base.rules.values())+[unconditional]+list(base.candidates.values()))
        conditional=ConditionalRule(
            "guarded",eq(f("f",v("?x")),f("g",v("?x"))),
            (("?x","S"),),(eq(f("mark",v("?x")),c("e")),),
            "explicit conditional fixture", "reviewed")
        candidate=replace(conditional,id="candidate_rule",
                          equation=eq(f("f",v("?x")),f("bad",v("?x"))),
                          status="candidate")
        return ConditionalBook(base,[conditional,candidate])

    def test_verified_guard_and_context_rewrite(self):
        book=self.fixture()
        goal=eq(f("h",f("f",c("a"))),f("h",f("g",c("a"))))
        outcome=prove_guarded(book,goal,max_steps=2)
        self.assertIsNotNone(outcome.certificate,outcome)
        step=outcome.certificate.steps[0]
        self.assertEqual(step.rewrite.rule_id,"guarded")
        self.assertEqual(step.rewrite.position,(0,))
        self.assertEqual(len(step.guards),1)
        self.assertTrue(verify_guarded_certificate(book,outcome.certificate,goal))

    def test_guard_absent_and_candidate_quarantine(self):
        book=self.fixture()
        self.assertIsNone(prove_guarded(book,eq(f("f",c("b")),f("g",c("b"))),
                                       max_steps=2).certificate)
        self.assertIsNone(prove_guarded(book,eq(f("f",c("a")),f("bad",c("a"))),
                                       max_steps=2).certificate)

    def test_local_guard_assumption_and_proof_isolation(self):
        book=self.fixture()
        goal=eq(f("g",c("b")),f("f",c("b")))
        hypothesis=eq(f("mark",c("b")),c("e"))
        self.assertIsNone(prove_guarded(book,goal,max_steps=1).certificate)
        answer=prove_guarded(book,goal,assumptions=(hypothesis,),max_steps=1)
        self.assertIsNotNone(answer.certificate)
        self.assertTrue(answer.certificate.steps[0].rewrite.reverse)
        self.assertTrue(verify_guarded_certificate(book,answer.certificate,goal,
                                                   assumptions=(hypothesis,)))
        self.assertFalse(verify_guarded_certificate(book,answer.certificate,goal,
                                                    assumptions=()))

    def test_tampered_guard_and_unsupported_rule_blocked(self):
        book=self.fixture()
        goal=eq(f("f",c("a")),f("g",c("a")))
        cert=prove_guarded(book,goal).certificate
        step=cert.steps[0]
        forged_guard=replace(step.guards[0],rulebook_sha256="0"*64)
        falses=(
            replace(cert,steps=(replace(step,guards=()),)),
            replace(cert,steps=(replace(step,guards=(forged_guard,)),)),
            replace(cert,steps=(replace(step,rewrite=replace(
                step.rewrite,rule_id="candidate_rule")),)),
            replace(cert,steps=(replace(step,rewrite=replace(
                step.rewrite,binding=(("?x",c("b")),))),)),
        )
        for bad in falses:
            with self.subTest(bad=bad):
                self.assertFalse(verify_guarded_certificate(book,bad,goal))

    def test_source_change_invalidates_conditional_proof(self):
        book=self.fixture()
        goal=eq(f("f",c("a")),f("g",c("a")))
        cert=prove_guarded(book,goal).certificate
        modified=[replace(rule,source=rule.source+" edited")
                  for rule in book.rules.values()]
        changed=ConditionalBook(book.base, modified+list(book.candidates.values()))
        self.assertFalse(verify_guarded_certificate(changed,cert,goal))

    def test_condition_cannot_introduce_fresh_variable(self):
        base=base_book()
        bad=ConditionalRule("bad",eq(f("f",v("?x")),f("g",v("?x"))),
             (("?x","S"),("?y","S")),(eq(v("?y"),c("a")),),
             "synthetic","reviewed")
        with self.assertRaises(ValueError):
            ConditionalBook(base,[bad])

    def test_conditional_guard_budget_no_false_proof(self):
        book=self.fixture()
        goal=eq(f("f",c("a")),f("g",c("a")))
        self.assertIsNone(prove_guarded(book,goal,max_guard_steps=0).certificate)
        self.assertIsNone(prove_guarded(book,goal,max_guard_attempts=1,
                                       max_guard_states=1).certificate)


class RouterIntegrationTests(unittest.TestCase):
    @staticmethod
    def c(name): return {"const":name}
    @staticmethod
    def v(name): return {"var":name}
    @staticmethod
    def app(name,*args): return {"app":name,"args":list(args)}

    def finite_data(self):
        c,v,f=self.c,self.v,self.app
        return {"logic":"finite_equational",
          "signature":{"sorts":["S"],"constants":{"a":"S","e":"S"},
                       "functions":{"mul":{"args":["S","S"],"returns":"S"}}},
          "rules":[{"id":"identity","variables":{"?x":"S"},
                    "source":"fixture","status":"reviewed",
                    "left":f("mul",v("?x"),c("e")),"right":v("?x")}],
          "assumptions":[],
          "goal":{"forall":{"var":"?x","sort":"S","body":{
              "eq":{"left":f("mul",v("?x"),c("e")),"right":v("?x")}}}}}

    def guarded_data(self):
        c,v,f=self.c,self.v,self.app
        return {"logic":"conditional_equational",
          "signature":{"sorts":["S"],"constants":{"a":"S","e":"S"},
                       "functions":{"f":{"args":["S"],"returns":"S"},
                                    "g":{"args":["S"],"returns":"S"},
                                    "mark":{"args":["S"],"returns":"S"}}},
          "rules":[{"id":"mark_a","variables":{},"source":"fixture","status":"reviewed",
                    "left":f("mark",c("a")),"right":c("e")}],
          "conditional_rules":[{"id":"guarded","variables":{"?x":"S"},
              "source":"fixture","status":"reviewed",
              "guards":[{"left":f("mark",v("?x")),"right":c("e")}],
              "left":f("f",v("?x")),"right":f("g",v("?x"))}],
          "assumptions":[],
          "goal":{"left":f("f",c("a")),"right":f("g",c("a"))}}

    def test_finite_router_and_tampering(self):
        task=self.finite_data()
        report=solve_problem(task,max_steps=3)
        self.assertTrue(report["certificate_replayed"],report)
        self.assertTrue(verify_problem(task,json.loads(json.dumps(report))))
        modified=copy.deepcopy(report)
        modified["certificate"]["proof"]["leaves"].pop()
        self.assertFalse(verify_problem(task,modified))
        altered=copy.deepcopy(task)
        altered["rules"][0]["status"]="candidate"
        self.assertFalse(verify_problem(altered,report))

    def test_conditional_router_and_tampering(self):
        task=self.guarded_data()
        report=solve_problem(task,max_steps=2)
        self.assertTrue(report["certificate_replayed"],report)
        self.assertTrue(verify_problem(task,json.loads(json.dumps(report))))
        altered=copy.deepcopy(task)
        altered["conditional_rules"][0]["status"]="candidate"
        self.assertFalse(verify_problem(altered,report))
        broken=copy.deepcopy(report)
        broken["certificate"]["steps"][0]["guards"]=[]
        self.assertFalse(verify_problem(task,broken))

    def test_unknown_logic_not_autoguessed(self):
        task=self.finite_data()
        task.pop("logic")
        with self.assertRaises(ValueError):
            solve_problem(task)


class ManySortedRegressionTests(unittest.TestCase):
    def test_polymorphic_forgery_rejected_in_base_logic(self):
        # x:S = f(x):S must NOT be applied with x:=t:T.
        book=EquationBook(["S","T"],{"a":"S","t":"T","u":"T"},
            {"f":(("S",),"S")},[
               RewriteRule("expand",eq(v("?x"),f("f",v("?x"))),
                           (("?x","S"),),"fixture","reviewed")])
        outcome=prove_equation(book,eq(c("t"),c("u")),max_steps=3)
        self.assertIsNone(outcome.certificate)


if __name__ == "__main__":
    unittest.main()
