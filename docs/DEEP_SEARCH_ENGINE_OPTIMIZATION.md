# Deep-search engine optimization: phase 1

This branch begins a staged optimization of the generic MCTS engine. It does not claim a universal search-quality improvement; each policy change must be measured against a fixed-budget baseline.

## Phase 1: separate selection from backup

Previously, the problem's `value_op` implicitly controlled both:
- the statistic backed up to a node (`mean` or best observed value), and
- the exploitation term used by UCT/PUCT selection.

These are different decisions. A max-backup problem can overvalue a branch because one noisy rollout produced an unusually high score. The engine now retains both the sample mean and the best observed return for every node, while preserving `value_op` as the default selection behavior.

The new optional argument is:

- `selection_value="backup"`: compatibility mode; uses the existing `Problem.node_value` semantics.
- `selection_value="mean"`: uses empirical mean for the exploitation term while still retaining best-so-far values for max-backup and final extraction.
- `selection_value="max"`: uses best observed return for exploitation, independent of the backup objective.

The default remains `"backup"`; existing callers need not change. `root.stats["selection_value"]` records the chosen policy.

## How to evaluate it

Compare `backup`, `mean`, and `max` under identical:
- problem instances and action-generation order,
- random seeds (paired runs),
- simulation/iteration budgets and maximum depth,
- wall-clock and peak-memory measurement protocols.

Record success rate, best observed score, mean score, created nodes, action-generation count, elapsed time, and run-to-run variance. Report distributions across seeds, not a single best run. Do not promote a new default merely because it wins on one fixture.

## Phase 2: best-observed trajectory traceability

The root node now exposes:
- `root.best_observed`: highest observed simulation/reward value.
- `root.best_trajectory`: the tree prefix plus rollout actions for that best observation, when available.
- `root.best_trajectory_complete`: whether the engine knows the full action trace.
- matching summary fields in `root.stats`.

The existing return value from `mcts()` remains the established tree-extraction policy for compatibility. The separate trajectory archive prevents callers from mistaking that policy path for the exact rollout that generated the best score. If a problem overrides `simulate()` without implementing `simulate_with_trace()`, the rollout is opaque; the engine records only the known tree prefix and explicitly marks the trace incomplete. Stream mode uses the selected tree prefix as a complete trace because it evaluates the current node directly.

The regression test replays a best trajectory through the problem's transition function and checks that its terminal reward matches the recorded best observation. This is a trace-consistency check, not a guarantee that the trajectory is optimal.

## Next engineering stages

1. **State identity and duplicate control:** add opt-in canonical state keys, local duplicate-action/state suppression, and explicit cycle handling without silently merging nodes whose histories affect rewards.
3. **Budget accounting:** separately cap expansions, action-generation work, rollout depth, retrieval calls, and elapsed time; report which budget stopped the run.
4. **Progressive widening and exploration:** evaluate diverse candidate admission, adaptive widening and exploration schedules against the existing policy; preserve stream ordering bias as an explicit property.
5. **Benchmark suite:** paired seeds, adversarial sparse-reward and deceptive-reward cases, wide/deep synthetic graphs, and regression checks. Timing is reported, not asserted in CI.
6. **Only after evidence:** consider parallel search, transposition DAGs, and more complex controllers; each requires its own consistency and concurrency tests.

## Status

Phase 1 code and regression tests are included in this branch. CI execution and benchmark results must be checked before treating the change as validated. No claim is made here that mean selection is universally superior.


## Progressive-widening admission fairness (opt-in)

For PUCT, the default `admission_epsilon=0.0` preserves highest-prior-first
admission. Setting `admission_epsilon` in `[0, 1]` gives each expansion an
independent chance to admit a uniformly sampled remaining action instead.
This changes candidate admission only; the normalized prior remains attached
to its action and the PUCT selection formula is unchanged. At epsilon 1, the
admission order is uniform without replacement; at intermediate values, the
search mixes prior-ranked admission with randomized coverage. Use paired-seed
benchmarks before selecting a nonzero value: randomized admission can improve
coverage but can also spend budget on low-quality candidates. The setting is
ignored by UCT and defaults to legacy behavior.


## G5-C exact incremental product-defect evaluator

math_mcts/product_defect.py adds FiniteGroupProductDefect. For a finite group
and a subset A, it tracks the exact ordered-pair multiplicities
r(g)=#{(a,b) in A×A: ab=g} and the exact defect z=|G|-|A²|.
A one-element swap changes only products involving the removed or inserted
element, so it constructs O(|A|) multiplicity deltas rather than recomputing
all |A|² products. Search states keep sparse overlays and periodically compact
to bound lookup-chain depth; the default compaction interval is a heuristic
based on sqrt(|A|), clamped to 4–32, and can be overridden. This reduces transition arithmetic, but does not
by itself remove the O(|G|) initial universe representation or guarantee faster
end-to-end MCTS; benchmarks must include overlay lookups, compaction, and memory.
The full recomputation method is an independent audit oracle, not the fast path.
Tests compare incremental and full counts on cyclic and noncommutative finite
groups. No G5-C universal bound is claimed.
