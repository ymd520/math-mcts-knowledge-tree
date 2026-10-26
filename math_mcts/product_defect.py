"""Exact incremental evaluation of finite-group product defects.

For a finite group G and A subset G, tracks r_A(g) = |{(a,b) in A^2: ab=g}|
and z(A) = |G \\ A^2|. A single-element swap updates only O(|A|) product
multiplicities; states store sparse deltas against their ancestors and compact
periodically to bound lookup depth.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from math import gcd, isqrt
from dataclasses import dataclass
from typing import Callable, Generic, Hashable, Iterable, TypeVar

T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class ProductDefectState(Generic[T]):
    _owner: "FiniteGroupProductDefect[T]"
    parent: "ProductDefectState[T] | None"
    delta: dict[T, int]
    subset: frozenset[T]
    z: int
    depth: int

    def count(self, product: T) -> int:
        """Return the exact ordered-pair multiplicity of product."""
        node: ProductDefectState[T] | None = self
        total = 0
        while node is not None:
            total += node.delta.get(product, 0)
            node = node.parent
        if total < 0:
            raise AssertionError("incremental product multiplicity became negative")
        return total

    def swap(self, remove: T, add: T) -> "ProductDefectState[T]":
        """Return the child state after replacing one member of A."""
        owner = self._owner
        if remove not in self.subset:
            raise ValueError("remove must belong to the current subset")
        if add in self.subset:
            raise ValueError("add must not belong to the current subset")
        if add not in owner.group:
            raise ValueError("add must be an element of the supplied group")

        remaining = self.subset - {remove}
        changes: Counter[T] = Counter()
        for a in remaining:
            changes[owner.multiply(remove, a)] -= 1
            changes[owner.multiply(a, remove)] -= 1
            changes[owner.multiply(add, a)] += 1
            changes[owner.multiply(a, add)] += 1
        changes[owner.multiply(remove, remove)] -= 1
        changes[owner.multiply(add, add)] += 1

        new_z = self.z
        sparse_delta: dict[T, int] = {}
        for product, change in changes.items():
            if not change:
                continue
            old_count = self.count(product)
            new_count = old_count + change
            if new_count < 0:
                raise AssertionError("swap update would create negative multiplicity")
            if old_count == 0 < new_count:
                new_z -= 1
            elif old_count > 0 == new_count:
                new_z += 1
            sparse_delta[product] = change

        child = ProductDefectState(
            _owner=owner,
            parent=self,
            delta=sparse_delta,
            subset=frozenset((*remaining, add)),
            z=new_z,
            depth=self.depth + 1,
        )
        if child.depth >= owner.compact_every:
            materialized = {}
            for g in owner.group:
                count = child.count(g)
                if count > 0:
                    materialized[g] = count
            return ProductDefectState(
                _owner=owner, parent=None, delta=materialized,
                subset=child.subset, z=child.z, depth=0,
            )
        return child


class FiniteGroupProductDefect(Generic[T]):
    """Exact evaluator for a supplied finite group.

    multiply must implement the group operation. Initialization costs O(|A|^2);
    each swap constructs O(|A|) product-count changes, with sparse lookups
    through at most compact_every overlay layers. If unspecified, compaction
    interval is heuristically chosen from sqrt(|A|), clamped to [4, 32].
    """

    def __init__(
        self,
        group_elements: Iterable[T],
        multiply: Callable[[T, T], T],
        initial_subset: Iterable[T],
        *,
        compact_every: int | None = None,
    ):
        if compact_every is not None and (
            type(compact_every) is not int or compact_every < 1
        ):
            raise ValueError("compact_every must be a positive integer or None")
        self.group = frozenset(group_elements)
        if not self.group:
            raise ValueError("group_elements must be nonempty")
        self.multiply = multiply
        initial_items = list(initial_subset)
        subset = frozenset(initial_items)
        if len(subset) != len(initial_items):
            raise ValueError("initial_subset must not contain duplicates")
        if not subset <= self.group:
            raise ValueError("initial_subset must be contained in group_elements")
        # Balance overlay lookup depth against the O(|G|) cost of compaction.
        # For |G|=m^2, sqrt(m) is a useful conservative starting point.
        self.compact_every = (compact_every if compact_every is not None
                              else max(4, min(32, isqrt(max(1, len(subset))))))

        counts: Counter[T] = Counter()
        for a in subset:
            for b in subset:
                product = multiply(a, b)
                if product not in self.group:
                    raise ValueError("multiply returned an element outside group_elements")
                counts[product] += 1
        self.initial_state = ProductDefectState(
            _owner=self, parent=None, delta=dict(counts), subset=subset,
            z=len(self.group) - len(counts), depth=0,
        )

    def recompute(self, subset: Iterable[T]) -> tuple[dict[T, int], int]:
        """Independent full recomputation, intended for audits and tests."""
        subset = frozenset(subset)
        if not subset <= self.group:
            raise ValueError("subset must be contained in group_elements")
        counts: Counter[T] = Counter(
            self.multiply(a, b) for a in subset for b in subset
        )
        if not counts.keys() <= self.group:
            raise ValueError("multiply returned an element outside group_elements")
        return dict(counts), len(self.group) - len(counts)


class ProductDefectSearchProblem:
    """Lazy swap-neighborhood adapter for the repository's generic MCTS engine.

    Use mcts(..., action_mode="stream", policy="uct", state_key=lambda s: s.subset).
    The affine permutation of the swap index space gives deterministic,
    seed-controlled coverage without materializing O(|A|(|G|-|A|)) actions.
    """

    value_op = "max"

    def __init__(self, evaluator: FiniteGroupProductDefect, *, seed: int = 0):
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        self.evaluator = evaluator
        self.seed = seed

    def initial_state(self) -> ProductDefectState:
        return self.evaluator.initial_state

    def iter_actions(self, state: ProductDefectState):
        remove_items = sorted(state.subset, key=repr)
        add_items = sorted(self.evaluator.group - state.subset, key=repr)
        width = len(add_items)
        total = len(remove_items) * width
        if total == 0:
            return
        stable_state = repr(tuple(sorted(state.subset, key=repr)))
        digest = sha256(f"{self.seed}|{stable_state}".encode("utf-8")).digest()
        if total == 1:
            multiplier = 1
        else:
            multiplier = 1 + (int.from_bytes(digest[:8], "big") % (total - 1))
            while gcd(multiplier, total) != 1:
                multiplier += 1
                if multiplier >= total:
                    multiplier = 1
        offset = int.from_bytes(digest[8:16], "big") % total
        for position in range(total):
            index = (multiplier * position + offset) % total
            remove_index, add_index = divmod(index, width)
            yield (remove_items[remove_index], add_items[add_index])

    def actions(self, state: ProductDefectState):
        """Eager compatibility interface; prefer iter_actions for wide states."""
        return list(self.iter_actions(state))

    def step(self, state: ProductDefectState, action):
        remove, add = action
        return state.swap(remove, add)

    def terminal(self, state: ProductDefectState) -> bool:
        return False

    def reward(self, state: ProductDefectState) -> float:
        """MCTS maximizes reward, so negate the exact integer defect."""
        return -float(state.z)

