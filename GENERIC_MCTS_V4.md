# Generic Math-MCTS v4: indexed delta grounding, lazy branching, and opt-in budget adaptation

This release is a **general-purpose engineering optimization**. It does not
privilege any conjecture, problem family or branch of mathematics. It does not
create or verify new theorems.

## 1. Ground-rule generation: only revisit activated predicates

`math_mcts.incremental_graph.build_incremental_graph` was already available.
The new implementation additionally indexes every reviewed Horn rule by its
premise **predicate** and activates that rule only when a fact of that
predicate became available in the previous synchronous round.

This changes repeated iteration over *all* selected rules into iteration over
only rules whose premises can have new matches. It preserves the existing
semi-naive delta join, original `RuleBook.instantiate` typing checks, precise
graph/round budgets, and certificate replay. If a rule has multiple premises
whose facts are new in the same round, only its first matching delta anchor
is admitted as a candidate. No legitimate ground edge is removed.

The `GraphBuildStats` report additionally tracks:
- `activated_rule_checks`: rule bodies inspected on the relevant rounds.
- `avoided_rule_checks`: conservative reference count of rule/round checks
  that are skipped (not a wall-time savings measurement).
- `duplicate_delta_anchors_skipped`: redundant multi-anchor candidates.
- `premise_match_attempts`: actual join fact-pattern probes.

**Boundary:** only positive, typed, ground Horn inference from previously
reviewed rules. A complete source graph proves a *relative* least fixed point,
not mathematical truth of the original source document. Truncation cannot
justify a non-derivability claim.

## 2. General MCTS: million-wide actions without eager materialization

`mcts(..., action_mode="stream")` now accepts an optional problem-specific
`Problem.iter_actions(state)` iterator. It only asks the iterator for an
action when progressive widening permits a new child.

This avoids the O(B) list allocation associated with `Problem.actions`
when the branching factor B is very large. Source code must **override
iter_actions** for genuine laziness: the default merely wraps `actions`.
The iterator's ordering is its search priority; unlike the original eager
UCT, stream mode **does not sample uniformly from all unexpanded actions**.

The streamed mode intentionally uses `Problem.reward(current_node_state)`
instead of the default random rollout. This prevents a hidden eager
`actions()` call during simulation. Intermediate-state reward functions
must be meaningful for the problem; zero scores may be uninformative for
sparse-reward tasks. This mode should be evaluated empirically before use.

```python
from math_mcts.mcts import Problem, mcts

class LargeProblem(Problem):
    def initial_state(self):
        return 0
    def actions(self, state):
        raise RuntimeError("Eager actions intentionally disabled")
    def iter_actions(self, state):
        return iter(range(1_000_000)) if state == 0 else iter(())
    def step(self, state, action):
        return ("leaf", action)
    def terminal(self, state):
        return state != 0
    def reward(self, state):
        return 1.0 if state == ("leaf", 0) else 0.0

path, tree = mcts(LargeProblem(), iterations=20, seed=7,
                  action_mode="stream", policy="uct")
print(tree.stats["yielded_actions"], tree.stats["created_nodes"])
```

Streaming + `policy="puct"` is deliberately rejected. PUCT expects
normalized priors across the *complete* sibling action set, which cannot
be honestly computed from an unbounded unseen iterator. Existing eager
UCT/PUCT semantics and defaults remain unchanged.

## 3. Optional plateau-based budget controller

`mcts(..., plateau_patience=25, min_plateau_iterations=100)` stops after
no **strictly improved observed rollout value** has occurred for the
chosen patience period, but only after the chosen minimum evaluations.
Both are optional; **default search still consumes all requested iterations**.

A plateau is a *search heuristic*. It is not a mathematical impossibility
certificate, a proof of optimality, or a measure of convergence. Sparse
rewards can plateau before valuable branches are examined. The controller
must be evaluated against fixed-budget baselines on unseen problems.

## 4. Observability and adversarial regression

`root.stats` additionally exposes:
`action_mode`, `yielded_actions`, `stream_exhausted_nodes`,
and `plateau_stop`, as well as existing iteration and node statistics.

```bash
python tests/test_generic_search_v4.py
python tests/test_incremental_graph.py
python tests/test_mcts.py
python tools/benchmark_generic_v4.py --chain 100 --width 60000 --iterations 15
```

The new tests compare full ground hyperedge sets to the independent reference
builder across generated cases, including multi-anchor facts, missing
premises and budget truncation. They also use a million-choice generator
whose eager `actions()` method deliberately raises an exception.

The benchmark reports source-record consumption, created nodes, exact
rule-activation counts and wall-time for synthetic tasks. The two search
modes do **not** have equal action sampling distributions or rollout
semantics; do not infer universal speedups or better mathematical search
quality from small fixture timings.

## 5. Architecture progression

Next steps for a **general** original-mathematics research engine are:
- broad, held-out diverse mathematical problem suites with explicit
  discovery objectives and independent counterexample auditing;
- typed transformations beyond function-free Horn logic, with genuine
  independent proof checking;
- controlled calibration of state scores, breadth/depth decisions and
  coverage/novelty metrics, preserving a strict candidate/verified barrier.

No canonical manifest version or curated knowledge count is changed by
these engineering changes.
