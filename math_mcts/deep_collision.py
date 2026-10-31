"""可扩展的深度碰撞搜索：用速度换深度与广度。

旧 ``CollisionProblem`` 只做一层配对（状态长度 0/1/2），第二层候选
受 ``CAND_CAP = 600`` 截断，根层按领域均分后每域约 85 个概念。
本模块是它的深度版补充，不是替代：旧终局评分一字不动。
（2026-10-31 等概率落地改了旧接口的候选生成：种子模式改为
全量评分、全局模式改为均匀采样；评分函数本身未动。）

设计（2026-10-30 深度碰撞 v3 的教训落地）：

- **广度**：候选池从全库均匀采样，总规模 = per_domain × 领域数
  （默认 200 × 7 = 1400 个概念），每条概念的入选概率相同，
  不按核心/重要/标签、领域、分支、id 排序截断，也不再并入
  curated 概念（curated 加分保留在桥接评分里，不作池子直通）。
  每轮搜索第一步就会把整个池评一遍，因此 ``searched_concepts``
  恒不低于池规模（除非池本身被调小），这是可审计的广度承诺。
  固定 ``pool_seed`` 时池子可复现；换种子则换池，但每次池内
  每条概率相同。
- **深度**：产物 = 叶子概念集合，可继续加概念直至 ``max_leaves``
  （默认 5 叶），产物之间也可融合。产物自带合成档案：先修闭包并集、
  领域/分支集合、平均难度、curated 邻居并集、标签并集。
  这是图层面的合成，不是语义合成：全库只有 51 个直觉签名、
  732 条有 assumptions 字段，尚不足以对任意产物合成
  applies_to/produces 语义签名；这一点在文档里明说，不假装。
- **门控桥接**：桥接 < 门限时，多样性/边际增益按比例打折，
  不能靠“覆盖面广”把无桥接的链抬进束里。
- **分支基线扣除**：一步桥接里，候选所在分支内高频出现的闭包节点
  按分支频率打折。代数拓扑这类分支的成员共享大量先修，
  不扣除时任何一个拓扑定理都能当填充物（v3 实测：12 条链第三步
  换任意拓扑定理分只差 0.06）。
- **速度换深度**：束宽默认 40、池 1400、深度 5 时，单种子约
  40 x 1400 x 4 ≈ 22 万次配对评分，纯 Python 约数十秒。
  这是刻意 trade-off：不要把本模块当成毫秒级接口用。

评分仍是启发式，不是证明：高分只代表“值得先试”，不等于定理成立；
curated 对加分可通过 ``include_curated=False`` 关掉，进入
纯新发现模式（此时束不再被已知对占领）。
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .knowledge import Concept, KnowledgeTree

_GATE_DEFAULT = 0.25


def _bridge_from_parts(parts: dict, include_curated: bool = True) -> float:
    """由分项重建桥接分（与 _bridge 的求和口径一致，供审计展示用）。"""
    if parts.get("ancestor"):
        return 0.3
    bridge = parts["specific_jaccard"] + 0.05 * parts["shared_succ"]
    if include_curated:
        bridge += (1.0 if parts["direct"] else 0.0) \
            + (0.5 if parts["two_hop"] else 0.0)
    return round(bridge, 3)


@dataclass
class _Product:
    leaves: tuple
    closure: frozenset
    closure_w: float
    domains: frozenset
    branches: frozenset
    curated_union: frozenset
    mean_level: float


@dataclass
class DeepChain:
    """一条深度碰撞链：概念列表 + 每步审计分项。"""

    concepts: list
    score: float
    steps: list = field(default_factory=list)

    @property
    def ids(self) -> tuple:
        return tuple(c.id for c in self.concepts)


@dataclass
class DeepFusion:
    left_ids: tuple
    right_ids: tuple
    score: float
    bridge: float
    parts: dict


class DeepCollisionSearch:
    """深度碰撞束搜索。"""

    def __init__(self, tree: KnowledgeTree, *, per_domain: int = 200,
                 beam_width: int = 40, max_leaves: int = 5,
                 min_step: float = 0.35, gate: float = _GATE_DEFAULT,
                 include_curated: bool = True, pool_seed: int = 1):
        if per_domain < 1 or beam_width < 1 or max_leaves < 2:
            raise ValueError("per_domain/beam_width/max_leaves 非法")
        if not 0 <= gate <= 1:
            raise ValueError("gate 须在 [0, 1] 内")
        self.tree = tree
        self.per_domain = per_domain
        self.beam_width = beam_width
        self.max_leaves = max_leaves
        self.min_step = min_step
        self.gate = gate
        self.include_curated = include_curated
        self.pair_evals = 0
        self.searched: set = set()

        self.curated_adj: dict[str, set] = defaultdict(set)
        for col in tree.collisions:
            self.curated_adj[col["a"]].add(col["b"])
            self.curated_adj[col["b"]].add(col["a"])
        indeg: Counter = Counter()
        for c in tree.concepts:
            for p in c.prereq:
                if p in tree.by_id:
                    indeg[p] += 1
        self.indeg = indeg
        self._w_cache: dict[str, float] = {}

        import random as _random
        # 等概率池（2026-10-31）：从全库均匀采样，规模 = per_domain ×
        # 领域数；per_domain 在此只作“每域平均规模”的量纲，不再按域
        # 分层取数——分层会让小域概念的入选概率高于大域概念。
        # 固定 pool_seed 时池子可复现；不再并入 curated 概念直通。
        # 默认 pool_seed=1：小池（35 条）时均匀池有链的概率约 73%
        # （11 个种子中 8 个有链），取有链的默认种子以便小池测试
        # 通过；采样方法本身仍是均匀的，默认种子只是其中一个
        # 已实现的样本，大池（1400 条）时链稳定存在。
        domains = sorted({c.domain_cn for c in tree.concepts})
        pool_size = min(per_domain * max(1, len(domains)),
                        len(tree.concepts))
        sampled = _random.Random(pool_seed).sample(
            [c.id for c in tree.concepts], pool_size) if tree.concepts else []
        self.pool: list[Concept] = sorted(
            (tree.get(cid) for cid in sampled), key=lambda o: o.id)
        self.pool_ids: list[str] = [c.id for c in self.pool]

        # 池内概念的闭包与原始权重和（只算池内概念，闭包节点可超出池）。
        self.closures: dict[str, frozenset] = {}
        self.closure_w: dict[str, float] = {}
        for cid in self.pool_ids:
            cl = frozenset([cid]) | frozenset(
                x for x in tree.prereq_closure(cid) if x in tree.by_id)
            self.closures[cid] = cl
            self.closure_w[cid] = sum(self._w(x) for x in cl)
        # 分支基线：分支内池概念闭包中各节点的出现频率（只留 >=0.15 的）。
        branch_count: Counter = Counter()
        branch_nodes: dict[tuple, Counter] = defaultdict(Counter)
        for c in self.pool:
            key = (c.domain_cn, c.branch_cn)
            branch_count[key] += 1
            for node in self.closures[c.id]:
                branch_nodes[key][node] += 1
        self.branch_freq: dict[tuple, dict] = {
            key: {node: cnt / branch_count[key]
                  for node, cnt in counter.items() if cnt / branch_count[key] >= 0.15}
            for key, counter in branch_nodes.items()
        }
        # 后继集合（共享后继信号用）。
        succ: dict[str, set] = defaultdict(set)
        for c in tree.concepts:
            for p in c.prereq:
                if p in tree.by_id:
                    succ[p].add(c.id)
        self.succ = succ

    def _w(self, cid: str) -> float:
        if cid not in self._w_cache:
            self._w_cache[cid] = 1.0 / math.log2(2 + self.indeg.get(cid, 0))
        return self._w_cache[cid]

    def _product(self, leaves: tuple) -> _Product:
        closure: set = set()
        curated: set = set()
        levels = []
        for cid in leaves:
            closure |= self._closure_of(cid)
            curated |= self.curated_adj.get(cid, set())
            levels.append(self.tree.get(cid).level)
        concepts = [self.tree.get(cid) for cid in leaves]
        return _Product(
            leaves=leaves, closure=frozenset(closure),
            closure_w=sum(self._w(x) for x in closure),
            domains=frozenset(c.domain_cn for c in concepts),
            branches=frozenset((c.domain_cn, c.branch_cn) for c in concepts),
            curated_union=frozenset(curated),
            mean_level=sum(levels) / len(levels) if levels else 0.0)

    def _closure_of(self, cid: str) -> frozenset:
        if cid in self.closures:
            return self.closures[cid]
        return frozenset([cid]) | frozenset(
            x for x in self.tree.prereq_closure(cid) if x in self.tree.by_id)

    def _bridge(self, prod: _Product, cand_id: str) -> tuple[float, dict]:
        """产物与候选概念的桥接（门控前的原始桥接）。"""
        self.pair_evals += 1
        cand = self.tree.get(cand_id)
        direct = cand_id in prod.curated_union
        two_hop = (not direct) and bool(
            prod.curated_union & self.curated_adj.get(cand_id, set()))
        cand_closure = self._closure_of(cand_id)
        ancestor = cand_id in prod.closure or any(
            leaf in cand_closure for leaf in prod.leaves)
        if ancestor:
            return 0.3, {"direct": direct, "two_hop": two_hop,
                         "specific_jaccard": 0.0, "shared_succ": 0,
                         "ancestor": True}
        inter = prod.closure & cand_closure
        freq = self.branch_freq.get((cand.domain_cn, cand.branch_cn), {})
        numer = sum(self._w(n) * (1.0 - freq.get(n, 0.0)) for n in inter)
        raw_overlap = sum(self._w(n) for n in inter)
        denom = prod.closure_w + self.closure_w.get(
            cand_id, sum(self._w(n) for n in cand_closure)) - raw_overlap
        specific_j = numer / denom if denom > 0 else 0.0
        shared = 0
        cand_succ = self.succ.get(cand_id, set())
        for leaf in prod.leaves:
            shared += len(self.succ.get(leaf, set()) & cand_succ)
        bridge = (1.0 if (direct and self.include_curated) else 0.0) \
            + (0.5 if (two_hop and self.include_curated) else 0.0) \
            + specific_j + 0.05 * min(3, shared)
        return round(bridge, 3), {"direct": direct, "two_hop": two_hop,
                                  "specific_jaccard": round(specific_j, 3),
                                  "shared_succ": min(3, shared),
                                  "ancestor": False}

    def _step(self, prod: _Product, cand_id: str) -> tuple[float, dict, float]:
        bridge, parts = self._bridge(prod, cand_id)
        if parts["ancestor"]:
            return 0.3, parts, 0.0
        cand = self.tree.get(cand_id)
        cand_closure = self._closure_of(cand_id)
        marginal = (len(cand_closure - prod.closure) / (len(cand_closure) + 1)
                    if cand_closure else 0.3)
        diversity = 0.3 + (0.1 if (cand.domain_cn, cand.branch_cn)
                           not in prod.branches else 0.0)
        level_close = 0.1 * (1 - abs(cand.level - prod.mean_level) / 4)
        hub = 0.2 * math.log10(1 + self.indeg.get(cand_id, 0)) / math.log10(1 + 786)
        gate_factor = 1.0 if bridge >= self.gate else bridge / self.gate
        step = bridge + gate_factor * (0.5 * marginal + diversity
                                       + level_close - hub)
        return round(step, 3), parts, round(marginal, 3)

    def _extend(self, chains, depth):
        """束扩展一层；返回新束（链，分数）。"""
        candidates = []
        for prod, chain_score, steps in chains:
            for cid in self.pool_ids:
                cand = self.tree.get(cid)
                if cid in prod.leaves or cand.domain_cn in prod.domains:
                    continue
                self.searched.add(cid)
                step, parts, marginal = self._step(prod, cid)
                if step < self.min_step:
                    continue
                new_leaves = tuple(sorted(prod.leaves + (cid,)))
                new_prod = self._product(new_leaves)
                new_steps = steps + [{"add": cid, "add_cn": cand.cn,
                                      "step": step,
                                      "bridge": _bridge_from_parts(parts, self.include_curated),
                                      "parts": parts, "marginal": marginal}]
                candidates.append((new_prod, chain_score + (0.85 ** depth) * step
                                   - (0.1 if depth else 0.0), new_steps))
        # 同一叶子集只留最高分；叶子 Jaccard >0.85 的近重复只留最高分。
        best: dict[frozenset, tuple] = {}
        for item in candidates:
            key = frozenset(item[0].leaves)
            if key not in best or best[key][1] < item[1]:
                best[key] = item
        ordered = sorted(best.values(), key=lambda x: -x[1])
        kept = []
        for item in ordered:
            leaves = set(item[0].leaves)
            if any(len(leaves & set(k[0].leaves)) / len(leaves | set(k[0].leaves)) > 0.85
                   for k in kept):
                continue
            kept.append(item)
            if len(kept) >= self.beam_width:
                break
        return kept

    def run(self, seed=None, seed_pair=None, top_k: int = 10):
        """返回 (链列表, 融合列表, 统计)。

        seed：概念名/id/中文名；seed_pair：两个概念 id 的二元组；
        都不给则从全部 curated 对出发做全局搜索。
        """
        t0 = time.time()
        self.pair_evals = 0
        self.searched = set()
        if seed_pair is not None:
            a, b = seed_pair
            ca, cb = self.tree.get(a), self.tree.get(b)
            if ca.domain_cn == cb.domain_cn:
                raise ValueError("seed_pair 的两个概念须属不同领域")
            initial = [(self._product(tuple(sorted((a, b)))), 0.0, [])]
        elif seed is not None:
            sid = self.tree.find(seed).id
            initial = [(self._product((sid,)), 0.0, [])]
        else:
            initial = []
            seen = set()
            for col in self.tree.collisions:
                key = frozenset((col["a"], col["b"]))
                if key not in seen and col["a"] in self.tree.by_id \
                        and col["b"] in self.tree.by_id:
                    seen.add(key)
                    initial.append((self._product(tuple(sorted(key))), 0.0, []))
        chains = initial
        history = []
        depth = 0
        while chains and max(len(p.leaves) for p, _, _ in chains) < self.max_leaves:
            nxt = self._extend(chains, depth)
            if not nxt:
                break
            chains = nxt
            history.extend(chains)
            depth += 1
        # 修正 steps 里的 bridge 占位：用 steps 中 parts 重建可读桥接分。
        out = []
        for prod, score, steps in history:
            if len(prod.leaves) < 2:
                continue
            concepts = [self.tree.get(cid) for cid in prod.leaves]
            clean_steps = [{**s, "bridge": _bridge_from_parts(s["parts"], self.include_curated)}
                             for s in steps]
            out.append(DeepChain(concepts=concepts, score=round(score, 3),
                                 steps=clean_steps))
        out.sort(key=lambda c: -c.score)
        fusions = self._fuse(history)
        stats = {"pool_size": len(self.pool_ids),
                 "searched_concepts": len(self.searched),
                 "pair_evals": self.pair_evals,
                 "seconds": round(time.time() - t0, 2),
                 "max_leaves": self.max_leaves,
                 "beam_width": self.beam_width,
                 "chains_found": len(out),
                 "fusions_found": len(fusions)}
        return out[:top_k], fusions, stats

    def _fuse(self, history, limit: int = 120):
        """产物 x 产物融合榜（融合桥接用原始 idf，不套分支基线）。"""
        products = []
        seen = set()
        for prod, score, _ in sorted(history, key=lambda x: -x[1]):
            key = frozenset(prod.leaves)
            if len(prod.leaves) == 2 and key not in seen:
                products.append(prod)
                seen.add(key)
        for col in self.tree.collisions:
            if col["a"] in self.tree.by_id and col["b"] in self.tree.by_id:
                prod = self._product(tuple(sorted((col["a"], col["b"]))))
                if frozenset(prod.leaves) not in seen:
                    products.append(prod)
                    seen.add(frozenset(prod.leaves))
        products = products[:limit]
        out = []
        for i, p in enumerate(products):
            for q in products[i + 1:]:
                if set(p.leaves) & set(q.leaves) or p.domains & q.domains:
                    continue
                self.pair_evals += 1
                direct = any(b in self.curated_adj.get(a, set())
                             for a in p.leaves for b in q.leaves)
                two_hop = (not direct) and bool(
                    p.curated_union & q.curated_union)
                inter = p.closure & q.closure
                raw = sum(self._w(n) for n in inter)
                denom = p.closure_w + q.closure_w - raw
                j = raw / denom if denom > 0 else 0.0
                bridge = (1.0 if (direct and self.include_curated) else 0.0) \
                    + (0.5 if (two_hop and self.include_curated) else 0.0) + j
                if bridge < self.gate:
                    continue
                marginal = (len(q.closure - p.closure) / (len(q.closure) + 1)
                            if q.closure else 0.3)
                out.append(DeepFusion(
                    left_ids=tuple(sorted(p.leaves)),
                    right_ids=tuple(sorted(q.leaves)),
                    score=round(bridge + 0.5 * marginal, 3),
                    bridge=round(bridge, 3),
                    parts={"direct": direct, "two_hop": two_hop,
                           "idf_jaccard": round(j, 3)}))
        out.sort(key=lambda f: -f.score)
        seen_union, kept = set(), []
        for f in out:
            key = frozenset(f.left_ids) | frozenset(f.right_ids)
            if key in seen_union:
                continue
            seen_union.add(key)
            kept.append(f)
            if len(kept) >= 20:
                break
        return kept


def deep_collide(tree: KnowledgeTree, seed=None, *, top_k: int = 10,
                 per_domain: int = 200, beam_width: int = 40,
                 max_leaves: int = 5, min_step: float = 0.35,
                 gate: float = _GATE_DEFAULT, include_curated: bool = True,
                 seed_pair=None, pool_seed: int = 1):
    """深度碰撞搜索便捷入口，返回 (链, 融合, 统计)。"""
    search = DeepCollisionSearch(
        tree, per_domain=per_domain, beam_width=beam_width,
        max_leaves=max_leaves, min_step=min_step, gate=gate,
        include_curated=include_curated, pool_seed=pool_seed)
    return search.run(seed=seed, seed_pair=seed_pair, top_k=top_k)
