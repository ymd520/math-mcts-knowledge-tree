"""Reproducible G5-C experiments on extraspecial 2-groups.

The exact-n2 mode exhausts the restricted family where every element squares
to the same central involution and no inverse pair is selected twice.
The mcts mode compares bounded exact-lookahead admission budgets on that same
invariant family. Search output is experimental evidence, never a proof of a
universal G5-C bound.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import time
import sys
from pathlib import Path
from math import gcd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts.mcts import Problem, mcts
from math_mcts.product_defect import FiniteGroupProductDefect


def group_product(a, b, n):
    """Multiplication on E_n x C_2, encoded as (x, y, t, c)."""
    x, y, t, c = a
    xx, yy, tt, cc = b
    cocycle = (x & yy).bit_count() & 1
    return (x ^ xx, y ^ yy, t ^ tt ^ cocycle, c ^ cc)


def build_group(n):
    if type(n) is not int or n < 2:
        raise ValueError("n must be an integer >= 2")
    width = 1 << n
    return tuple((x, y, t, c)
                 for x in range(width)
                 for y in range(width)
                 for t in (0, 1)
                 for c in (0, 1))


def square_one_pair_keys(n):
    width = 1 << n
    return tuple((x, y, c)
                 for x in range(width)
                 for y in range(width)
                 if ((x & y).bit_count() & 1) == 1
                 for c in (0, 1))


def sample_initial_subset(n, seed):
    m = 1 << (n + 1)
    keys = square_one_pair_keys(n)
    if len(keys) < m:
        raise ValueError("candidate family is too small for this n")
    rng = random.Random(seed)
    selected = rng.sample(list(keys), m)
    return frozenset((x, y, rng.randrange(2), c) for x, y, c in selected)


class ConstrainedSquareOneProblem(Problem):
    """Swap search preserving square=a fixed central involution and no inverses."""

    value_op = "max"

    def __init__(self, evaluator, n, *, seed=0, candidate_sample_size=0):
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        if type(candidate_sample_size) is not int or candidate_sample_size < 0:
            raise ValueError("candidate_sample_size must be a nonnegative integer")
        self.evaluator = evaluator
        self.n = n
        self.seed = seed
        self.candidate_sample_size = candidate_sample_size
        self.candidate_evaluations = 0
        self.group_order = tuple(sorted(evaluator.group))
        self.group_index = {g: i for i, g in enumerate(self.group_order)}
        self.eligible = tuple(g for g in self.group_order
                              if ((g[0] & g[1]).bit_count() & 1) == 1)

    @staticmethod
    def pair_key(element):
        x, y, _t, c = element
        return (x, y, c)

    def initial_state(self):
        return self.evaluator.initial_state

    def iter_actions(self, state):
        remove_items = sorted(state.subset, key=self.group_index.__getitem__)
        add_items = [g for g in self.eligible if g not in state.subset]
        selected_keys = {self.pair_key(g) for g in state.subset}
        total = len(remove_items) * len(add_items)
        if total == 0:
            return
        signature = tuple(self.group_index[g] for g in remove_items)
        digest = hashlib.sha256(
            f"{self.seed}|{signature}".encode("utf-8")
        ).digest()
        if total == 1:
            multiplier = 1
        else:
            multiplier = 1 + int.from_bytes(digest[:8], "big") % (total - 1)
            while gcd(multiplier, total) != 1:
                multiplier += 1
                if multiplier >= total:
                    multiplier = 1
        offset = int.from_bytes(digest[8:16], "big") % total
        width = len(add_items)

        def action_at(position):
            index = (multiplier * position + offset) % total
            i, j = divmod(index, width)
            return remove_items[i], add_items[j]

        def admissible(action):
            remove, add = action
            add_key = self.pair_key(add)
            return add_key == self.pair_key(remove) or add_key not in selected_keys

        sample_size = self.candidate_sample_size
        sampled = []
        cutoff = -1
        if sample_size:
            for position in range(total):
                action = action_at(position)
                if not admissible(action):
                    continue
                sampled.append((position, action))
                if len(sampled) >= sample_size:
                    cutoff = position
                    break
            ranked = []
            for position, action in sampled:
                self.candidate_evaluations += 1
                ranked.append((state.swap(*action).z, position, action))
            for _, _, action in sorted(ranked, key=lambda item: (item[0], item[1])):
                yield action
            start = cutoff + 1
        else:
            start = 0

        for position in range(start, total):
            action = action_at(position)
            if admissible(action):
                yield action

    def actions(self, state):
        return list(self.iter_actions(state))

    def step(self, state, action):
        return state.swap(*action)

    def terminal(self, state):
        return False

    def reward(self, state):
        return -float(state.z)


def exact_n2_enumeration():
    n = 2
    group = build_group(n)
    group_index = {g: i for i, g in enumerate(group)}
    multiplication_table = [
        [group_index[group_product(a, b, n)] for b in group]
        for a in group
    ]
    keys = square_one_pair_keys(n)
    m = 1 << (n + 1)
    pair_elements = [((x, y, 0, c), (x, y, 1, c)) for x, y, c in keys]
    best = len(group) + 1
    minimizers = 0
    candidates = 0
    histogram = {}
    for selected in itertools.combinations(range(len(keys)), m):
        selected_pairs = [pair_elements[i] for i in selected]
        for bits in itertools.product((0, 1), repeat=m):
            subset_ids = [group_index[selected_pairs[j][bits[j]]]
                          for j in range(m)]
            covered = set()
            for a in subset_ids:
                row = multiplication_table[a]
                covered.update(row[b] for b in subset_ids)
            defect = len(group) - len(covered)
            candidates += 1
            histogram[defect] = histogram.get(defect, 0) + 1
            if defect < best:
                best, minimizers = defect, 1
            elif defect == best:
                minimizers += 1
    return {
        "mode": "exact-n2",
        "group_order": len(group),
        "m": m,
        "eligible_inverse_pair_count": len(keys),
        "candidate_count": candidates,
        "minimum_defect": best,
        "minimizer_count": minimizers,
        "defect_histogram": dict(sorted(histogram.items())),
        "scope": "restricted square-one, inverse-pair-free family only",
    }


def run_mcts(n, iterations, seeds, sample_sizes, max_nodes, depth, time_budget_seconds=None):
    group = build_group(n)
    rows = []
    for seed in seeds:
        initial_subset = sample_initial_subset(n, seed)
        for sample_size in sample_sizes:
            evaluator = FiniteGroupProductDefect(
                group, lambda a, b, n=n: group_product(a, b, n),
                initial_subset,
            )
            problem = ConstrainedSquareOneProblem(
                evaluator, n, seed=seed, candidate_sample_size=sample_size,
            )
            started = time.perf_counter()
            _, root = mcts(
                problem, iterations=iterations, seed=seed, max_depth=depth,
                max_nodes=max_nodes, action_mode="stream", policy="uct",
                selection_value="max", state_key=lambda state: state.subset,
                widening_k=2.0, widening_alpha=0.5,
                time_budget_seconds=time_budget_seconds,
            )
            elapsed = time.perf_counter() - started
            best_value = root.stats["best_observed_value"]
            rows.append({
                "n": n,
                "group_order": len(group),
                "m": 1 << (n + 1),
                "seed": seed,
                "candidate_sample_size": sample_size,
                "best_defect": None if best_value is None else int(-best_value),
                "simulations": root.stats["simulations"],
                "created_nodes": root.stats["created_nodes"],
                "candidate_evaluations": problem.candidate_evaluations,
                "elapsed_seconds": elapsed,
                "initial_defect": evaluator.initial_state.z,
                "stop_reason": root.stats["stop_reason"],
            })
    return {
        "mode": "mcts",
        "scope": "restricted square-one, inverse-pair-free family",
        "iterations_per_run": iterations,
        "max_nodes": max_nodes,
        "depth": depth,
        "time_budget_seconds": time_budget_seconds,
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("exact-n2", "mcts"), default="exact-n2")
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--seeds", type=int, nargs="+", default=[217, 2027])
    parser.add_argument("--candidate-sizes", type=int, nargs="+", default=[0, 16, 32])
    parser.add_argument("--max-nodes", type=int, default=300)
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--time-budget-seconds", type=float, default=None)
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    if args.mode == "exact-n2":
        result = exact_n2_enumeration()
    else:
        if args.n < 2 or args.iterations < 1 or args.max_nodes < 1 or args.depth < 1:
            parser.error("n >= 2, iterations/max-nodes/depth >= 1 are required")
        if args.time_budget_seconds is not None and args.time_budget_seconds <= 0:
            parser.error("time budget must be positive when supplied")
        if any(x < 0 for x in args.candidate_sizes):
            parser.error("candidate sizes must be nonnegative")
        result = run_mcts(args.n, args.iterations, args.seeds,
                          args.candidate_sizes, args.max_nodes, args.depth,
                          args.time_budget_seconds)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output == "-":
        print(text)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
