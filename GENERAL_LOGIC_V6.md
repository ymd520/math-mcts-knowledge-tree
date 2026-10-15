# Math-MCTS General Logic v6: finite binders and certified conditional identities

## Architecture contract (not a domain-specific solver)

The architecture still separates 1. source/provenance, 2. untrusted
discovery candidates, 3. explicitly reviewed type-checked rulebooks,
4. search/instantiation, 5. independent replay, 6. claims and limitations.

The new components **extend the equational branch** without modifying the
legacy positive-Horn engine or merging the two logics unsoundly:

```text
                  Knowledge + provenance
                          |
           Discovery / untrusted candidate
                          X  review required
                          |
                 Trusted assumption boundary
                    +-----+---------+
                    |               |
              Reviewed Horn    Reviewed EquationBook
                    |               |
           delta graph/closure +----+-----------------+
                    |          |                      |
                old MCTS    finite_logic          conditional_logic
                    |        (∀,∃,∧,∨,⇒)          (guards G₁..Gₖ ⇒ L=R)
                    |          |                      |
                    +----------+----------------------+
                               |
                  independent replay / exact scope
```

Here `reviewed` means **caller-accepted premise**, not verified mathematical
truth or a Lean kernel proof. Unreviewed, refuted or source-unmatched rules
cannot be used as proof steps. Search failures are never refutations.

## Safety fix in the underlying typed equation prover

Before this phase, a `?x:S` pattern occurring as an entire side of an
equation could match a ground term of sort `T` in search and replay.
Both `prove_equation` and `verify_rewrite_certificate` now check EVERY
matched variable against its declared sort, and reject ill-typed output.
This is an actual type-soundness fix, independently regression tested.

## Finite-domain quantified equality

`math_mcts.finite_logic` implements *bounded proof generation* for:
- ground typed equations (each leaf independently checked by the existing
  equational certificate checker);
- finite conjunction (`and`) and disjunction (`or`, branch named explicitly);
- typed `forall` and `exists` binders over ALL constants explicitly declared
  for that sort in the current EquationBook;
- explicit hypothetical implications `[ground equality premises] => body`.
  Each premise is added only to its own child proof's local assumption scope.
  The leaf certificates bind the exact premise list to their signatures.

`forall` certificates contain one checked child for EACH domain constant,
in deterministic sorted order. `exists` certificates name ONE real declared
witness; the verifier checks that witness belongs to the binder's exact sort.
Nested binders with shadowed names and undeclared/free variables are rejected.
The sort universe is fingerprinted in the EquationBook SHA256.

**CRUCIAL LIMITATION:** A finite enumeration does **not** prove a universally
quantified statement about all mathematical objects of a sort unless the
mathematical universe has separately been established to be exactly that
finite set. Even if all explicit constant cases pass, the engine cannot make
an unbounded universal theorem claim. In an empty declared domain,
`forall` is vacuously satisfied while `exists` has no witness.

The implementation has explicit `max_cases`, `max_nodes`,
`max_steps`, `max_states`, and `max_term_nodes` limits. Out-of-budget,
unknown or not-found does **not** imply false.

## Conditional equations with independent guard proofs

`math_mcts.conditional_logic` accepts explicitly reviewed and typed
schematic conditional identities:

```text
  G1(x)=H1(x), ..., Gk(x)=Hk(x)
  ----------------------------
                  L(x)=R(x)
```

To apply the consequent in either direction, the engine must instantiate
EVERY side condition from the rule's matched variables. It obtains a
separately checked `RewriteCertificate` for each ground guard using ONLY
the underlying unconditional EquationBook and the declared problem-local
equality assumptions. The step stores these subcertificates and the
independent `verify_guarded_certificate` checker replays all guards again,
then checks the actual parent transformation and its type.

Conditional rules cannot recursively justify their own guards, which avoids
circular self-proof. Every variable must occur on both sides of the main
rewrite, and conditions cannot introduce new variables/witnesses. Unmatched
side conditions make that candidate unavailable; no claim of guard falsity
or mathematical non-existence follows.

Resource bounds: `max_guard_attempts`, `max_guard_steps`,
`max_guard_states`, as well as step, state and term-size budgets.

**Not supported:** general quantified logic over infinite domains,
disjunction/negation inside guards, arbitrary existential witnesses,
dependent sorts, higher-order/binding operations, partial functions,
Lean source parsing, general cross-Horn/equational inference, or proof
of correctness of caller-reviewed source identities.

## Reproduce + independently verify

```sh
python tests/test_logic_v6.py
python tests/test_equational.py
python tools/solve_logic.py examples/finite_quantifier_implication.json --output finite_proof.json
python tools/solve_logic.py examples/finite_quantifier_implication.json --verify finite_proof.json
python tools/solve_logic.py examples/conditional_guarded_equality.json --output guarded_proof.json
python tools/solve_logic.py examples/conditional_guarded_equality.json --verify guarded_proof.json
```

For a safe but instructive test, the finite implication
`∀x∈{a,b}, (x=a => h(x)=h(a))` is checked with one local equality
assumption per instantiated case. This is a finite example and does not
assume any unsupplied axiom.

The conditional example proves `f(a)=g(a)` from a reviewed hypothetical
rule `mark(x)=ok => f(x)=g(x)` together with a separate unconditional
identity `mark(a)=ok`. An additional *candidate* conditional identity
is deliberately quarantined.

## Acceptance conditions

- All legacy MCTS, typed Horn, equational and catalog regressions pass.
- Python 3.10 and 3.12 both pass independent certificate checks.
- Universal proofs reject missing cases or altered domain fingerprints;
  existential proofs reject nonexistent/wrong-sort witnesses.
- Implication proofs reject forged or dropped antecedents.
- Conditional proofs reject missing, forged or recursive guard justifications.
- New logic never touches canonical catalog version or importance counts.

No verified novel mathematical theorem, unconditional first-order theorem
prover or universal speedup is claimed by these software changes.
