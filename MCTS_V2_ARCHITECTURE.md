# MCTS v2: ground-rule proof routing and research candidate boundary

## Why restructure the solver?

The original MCTS implementation randomly expanded legal branches even on
finite, ground, positive Horn-rule graphs where a standard forward saturation
can determine reachability and construct an independently replayed witness.
MCTS remains valuable for budgeted *search* under nontrivial search objectives,
but is not a substitute for deterministic logical closure when that exists.

This change separates three layers:

```text
Unreviewed source/Mathlib/text candidate (never active as a proof rule)
      ↓ explicit fingerprint-locked translation
Typechecked Rule(status="candidate"), UNTRUSTED (requires external review)
      ╳ NO AUTOMATIC PROMOTION
Explicitly reviewed typed RuleBook (unchanged trusted boundary)
      ↓ instantiate complete premises as ground Hyperedge
Event-driven Horn closure + proof dependency cone + certificate replay
      ↘ if an available proof witness is longer than max_steps,
         or graph is truncated, fallback to heuristic PUCT
         ↓ independent certificate replay before any success is returned
```

This architecture **does not** turn the imported 234,576 text declarations
into verified reusable mathematical theorems. It makes one particular already
reviewed, formalized class of logical reasoning more efficient and auditable.

## Deterministic closure engine

`math_mcts.hypergraph_closure.forward_certificate`:

1. Validates each ground hyperedge against the exact reviewed `RuleBook`.
2. Tracks missing premise counts and an incidence index; only when every
   premise is known does a conclusion become available.
3. Records the *first* valid producer of each new fact.
4. Extracts only the actual goal dependency cone, iteratively (also works
   beyond normal Python recursion limits).
5. Independently replays a `Certificate` whose SHA256 includes the RuleBook.
6. Returns the certificate only if its distinct dependency edges fit
   `max_steps`; an over-budget witness is reported without a success claim.

For a given prebuilt finite ground hypergraph, closure processing has
linear size complexity in the total number of ground edges, premise
occurrences and derived facts (excluding fingerprint validation, output
serialization and verification work). Building the ground graph itself
may be a much more expensive operation: do not claim an end-to-end
linear-time mathematical prover.

When the ground graph is marked `complete`, closure can correctly
report that the goal is not derivable from these finite reviewed Horn
rules. This does **not** refute arbitrary mathematical conjectures,
and an incomplete ground graph cannot establish nonderivability.

The first witness need not be the shortest. When it exceeds `max_steps`,
the solver falls back to budgeted PUCT: a longer witness is *not* proof that
no shorter witness exists.

## MCTS policy improvements

The default `mcts(...)` remains backward-compatible UCT.
Opt-in `policy="puct"` uses a nonnegative `Problem.action_weight`
prior to order progressive expansions and selects children with PUCT.
Weights are normalized once from the full action set and are not recomputed
each time an expansion occurs. Invalid/nonfinite weights are rejected.

`stop_on_success=True` stops only if `Problem.success_found()` reports an
actual witness. `DerivationProblem` signals success from a sequence of
*enabled* ground steps. A final certificate is still independently replayed.

Root `stats` exposes: requested iterations, actual rollouts, generated
tree nodes, guided expansions, policy and early-stop status. No global
merging of distinct MCTS tree nodes is performed (a fact-set transposition
does not automatically preserve the proof path); the existing bounded
state-action cache is retained.

`derive` now uses deterministic closure first, then guided PUCT.
`solve_adaptive` routes its MCTS branch through the same guided policy,
without changing its small-graph BFS / medium-graph beam routing.

## Typed translation proposals from external sources

The previous external candidate importer already requires the original
source project, pinned ref, locator and exact statement SHA-256.

A new `bridge` command takes a **separate manually written** JSON file
describing a possible translation into typed Horn predicates:

```json
{
  "signatures": {"P": ["T"], "Q": ["T"]},
  "objects": {"a": "T"},
  "candidates": [
    {
      "candidate_id": "EXT_REPLACE_WITH_IMPORTED_ID",
      "statement_sha256": "REPLACE_WITH_ACTUAL_SOURCE_SHA256",
      "variables": {"?x": "T"},
      "premises": [{"predicate": "P", "args": ["?x"]}],
      "conclusion": {"predicate": "Q", "args": ["?x"]},
      "status": "candidate"
    }
  ]
}
```

```sh
python tools/expand_knowledge.py bridge --db external_math.sqlite \
  --mapping candidate_translation.json
```

The command checks input sorts and binding completeness using the existing
`RuleBook`, and rejects altered source hashes or attempts to call an
unreviewed translation `reviewed`. Output remains `status=candidate` and
cannot be used as a proof rule.

This is *not* automatic translation, independent license checking or
Mathematical proof. It creates a safe human-review boundary for such tools.

## Reproduction and comparisons

```sh
python tests/test_mcts_v2.py
python tests/test_reasoning.py
python tests/test_lean_adaptive.py
python tools/benchmark_mcts_v2.py --iterations 180 --output mcts_v2_benchmark.json
```

The benchmark uses exactly the same prebuilt ground graph for closure,
classic UCT and guided PUCT, and reports measured simulations and elapsed
search time. One closure-edge scan is not equivalent to an MCTS simulation,
and timings vary by machine. Claims of speedups require repeated trials
and multiple realistic held-out datasets; none are asserted solely from
the toy benchmarks.

## Future engineering stages

1. Scalable extraction of faithful theorem types/arguments from fixed-source
   Mathlib environment; no missing Lean kernel attestation can be invented.
2. A source-compatible, independently reviewed mapping process with
   provenance signatures before promotion.
3. More expressive proof transformations (quantifiers, equality rewriting,
   function terms, non-Horn logic) with precise semantics and verification.
4. Heuristic action generation from verified method operators, typed
   preconditions, and targeted counterexamples.
5. Independent research-problem holdouts, performance profiles (including
   memory and candidate recall), cross-seed tests, comparison against exact
   solvers, and mathematical novelty audit.
6. Branches merged and deleted; catalog version changed only at the
   canonical manifest. No unrelated version edits.
