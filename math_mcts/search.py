"""基于 MCTS 的高层搜索接口.

1. plan_learning_path: 给定目标概念, 用 MCTS 在"前置依赖图"上规划
   一条从基础到目标的最优学习路径(动作=下一个要学的概念).
2. search_concepts: 给定关键词, 用 MCTS 在"领域->分支->主题->概念"
   的知识层级树上搜索最相关的概念(动作=沿层级下钻).
"""
from __future__ import annotations

import re
from collections import Counter

from .knowledge import Concept, KnowledgeTree
from .mcts import Problem, mcts


# ---------------------------------------------------------------- 学习路径
class LearningPathProblem(Problem):
    """状态: 已学概念 id 的有序元组. 动作: 下一个可学的概念 id."""

    def __init__(self, tree: KnowledgeTree, target: str, max_steps: int = 15,
                 known: list[str] | tuple[str, ...] = ()):
        self.tree = tree
        self.target = target
        self.max_steps = max_steps
        self.known = tuple(k for k in known if k in tree.by_id)
        # 规模优化: 预计算前置集合; MCTS 会反复访问相同状态, 缓存动作列表
        self._pre = [(c.id, frozenset(c.prereq))
                     for c in tree.concepts]
        self._act_cache: dict[tuple, list] = {}

    def initial_state(self):
        return self.known

    def actions(self, state) -> list:
        if state in self._act_cache:
            return self._act_cache[state]
        learned = frozenset(state)
        cands = sorted(cid for cid, pre in self._pre
                       if cid not in learned and pre <= learned)
        self._act_cache[state] = cands
        return cands

    def step(self, state, action):
        return state + (action,)

    def terminal(self, state) -> bool:
        return (self.target in state or not self.actions(state)
                or len(state) >= self.max_steps)

    def reward(self, state) -> float:
        if self.target in state:
            levels = [self.tree.get(cid).level for cid in state]
            # 难度跳跃惩罚: 相邻两步难度差超过 1 则扣分
            jumps = sum(max(0, b - a - 1) for a, b in zip(levels, levels[1:]))
            return max(0.05, 1.0 - 0.08 * jumps - 0.015 * len(state))
        # 未到达目标: 按"目标前置闭包覆盖率"给部分分
        need = set(self.tree.prereq_closure(self.target))
        if not need:
            return 0.0
        got = need & set(state)
        return 0.4 * len(got) / len(need)


def plan_learning_path(tree: KnowledgeTree, target: str,
                         max_steps: int = 15, iterations: int = 3000,
                         seed: int = 7,
                         known: list[str] | tuple[str, ...] = ()) -> list[Concept]:
    """Return an exact prerequisite-closed learning sequence without detours.

    The target dependency graph is known in full; a topological closure is
    deterministic, sound and cheaper than stochastic MCTS. The retained
    max_steps/iterations/seed parameters preserve the historical API but
    do not truncate required prerequisites or affect this exact plan.
    """
    concept = tree.find(target)
    already = {k for k in known if k in tree.by_id}
    if concept.id in already:
        # The target is already mastered. Keep the correct target identity for
        # downstream renderers without adding unrelated mastered concepts.
        return [concept]
    return [tree.get(cid) for cid in
            [*tree.prereq_closure(concept.id), concept.id] if cid not in already]


def export_path_markdown(path: list[Concept]) -> str:
    """把学习路径导出为 Markdown 学习计划."""
    target = path[-1]
    lines = [f"# 学习计划: {target.cn}({target.en})",
             "",
             f"共 {len(path)} 步, 按目标先修依赖拓扑顺序规划.",
             "",
             "| 步骤 | 概念 | 难度 | 位置 |",
             "|---|---|---|---|"]
    for i, c in enumerate(path, 1):
        mark = " 🎯" if i == len(path) else ""
        lines.append(f"| {i} | {c.cn}({c.en}){mark} | "
                     f"{c.level}/5 | {c.path()} |")
    lines += ["", "## 每步详解", ""]
    for i, c in enumerate(path, 1):
        lines.append(f"### {i}. {c.cn}")
        lines.append("")
        lines.append(c.definition)
        if c.formulas:
            lines.append("")
            lines.append("公式: " + " ; ".join(c.formulas))
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 概念检索
def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)          # 英文词
    tokens += [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]  # 中文单字
    return tokens


class ConceptSearchProblem(Problem):
    """状态: 层级树节点. 动作: 下钻到子节点. 终局: 到达概念叶节点.

    模拟步采用子树精确求值: 知识树完全已知、叶节点评分廉价,
    直接返回该子树下所有概念的最大相关度，作为UCB探索的评分信号。
    没有实现分支限界剪枝；有限迭代不保证找到全局最相关概念。

    回传方式为 max(见 Problem.value_op): 精确求值下均值回传会
    稀释父节点价值, 导致 UCB 错过藏着最优叶的分支.
    """

    value_op = "max"

    def __init__(self, tree: KnowledgeTree, query: str):
        self.tree = tree
        self.query = query
        self.qtok = Counter(_tokenize(query))
        self.qtotal = sum(self.qtok.values()) or 1
        # 规模优化: 查询确定后叶节点奖励是静态的, 预计算一次;
        # 再自底向上算出每个层级节点的子树最大奖励, simulate 变 O(1).
        self._leaf_reward: dict[str, float] = {}
        for c in tree.concepts:
            self._leaf_reward[c.id] = self._score_concept(c)
        self._submax: dict[tuple, float] = {}
        self._build_submax(())

    def _build_submax(self, node: tuple) -> float:
        if self.tree.is_concept_leaf(node):
            v = self._leaf_reward[node[1]]
        else:
            kids = self.tree.hierarchy_children(node)
            v = max((self._build_submax(ch) for ch in kids),
                    default=0.0)
        self._submax[node] = v
        return v

    def simulate(self, state, rng, max_depth: int) -> float:
        return self._submax.get(state, 0.0)

    def initial_state(self):
        return ()

    def actions(self, state) -> list:
        return self.tree.hierarchy_children(state)

    def step(self, state, action):
        return action

    def terminal(self, state) -> bool:
        return self.tree.is_concept_leaf(state)

    def _score_concept(self, c) -> float:
        ctok = Counter(_tokenize(c.text_blob()))
        overlap = sum(min(self.qtok[t], ctok.get(t, 0)) for t in self.qtok)
        score = overlap / self.qtotal
        # 名称命中加权: 查询词出现在概念名中是强相关信号
        q = self.query.strip().lower()
        if q and (q == c.cn.lower() or q == c.en.lower()):
            score += 1.0
        elif q and (q in c.cn.lower() or q in c.en.lower()):
            score += 0.6
        name_chars = set(_tokenize(c.cn + " " + c.en))
        hit = sum(1 for t in self.qtok if t in name_chars)
        score += 0.3 * hit / max(1, len(self.qtok))
        if "核心" in c.tags:
            score += 0.15
        return score

    def reward(self, state) -> float:
        if not self.tree.is_concept_leaf(state):
            return 0.0
        return self._leaf_reward[state[1]]


def collision_score(tree: KnowledgeTree, a: str, b: str) -> float:
    """概念对 (a,b) 的碰撞价值分.

    curated 碰撞记录 +2.0; 跨领域 +0.5; 双核心 +0.3;
    难度接近加分(同层概念更易组合出成果); 共享标签加分.
    """
    ca, cb = tree.get(a), tree.get(b)
    score = 0.0
    if tree.collision_note(a, b):
        score += 2.0
    if ca.domain_cn != cb.domain_cn:
        score += 0.5
    if "核心" in ca.tags and "核心" in cb.tags:
        score += 0.3
    score += 0.2 * (1 - abs(ca.level - cb.level) / 4)
    shared = set(ca.tags) & set(cb.tags) - {"核心"}
    score += 0.1 * min(2, len(shared))
    return round(score, 3)


class CollisionProblem(Problem):
    """知识碰撞: 状态=已选概念元组(长度0/1/2).

    动作=追加一个不同领域的概念, 终局=凑成一对.
    搜索树: 根 -> 第一个概念 -> 第二个概念(跨领域) -> 叶=碰撞对.
    模拟步用候选集合内精确求值，MCTS 做有界候选探索，
    回传方式为 max(同 ConceptSearchProblem 的理由).
    """

    value_op = "max"

    # 规模优化: 第二层候选上限. 概念数上千后全量配对是 O(N²),
    # 按"跨领域 + 标签优先级"截断, 既保证质量又保证速度.
    CAND_CAP = 600

    def __init__(self, tree: KnowledgeTree, seed: str | None = None):
        self.tree = tree
        self.seed = tree.find(seed).id if seed else None
        # 规模优化: 候选搭档改为懒计算. 原先 __init__ 里对每个概念全量配对
        # 是 O(N²)(4588 规模约 2100 万次比较, 23 万规模则不可行);
        # 现在只在 MCTS 实际访问到某个概念时才计算其候选, 并缓存.
        self._cands: dict[str, list[str]] = {}
        self._best_cache: dict[str, float] = {}
        # 根层候选也截断: 概念数上千后全量根动作会让 MCTS 在 4000 次迭代内
        # 一次也到不了第二层(4588 规模实测返回 0 对). 取标签优先级 top-K,
        # 再并上 curated 碰撞涉及的概念, 保证人工精选对仍可被发现.
        rank = {"核心": 0, "重要": 1}
        roots = sorted(tree.concepts,
                       key=lambda o: (min((rank.get(t, 2) for t in o.tags), default=2), o.id))
        curated = {col["a"] for col in tree.collisions} | \
                  {col["b"] for col in tree.collisions}
        # Ranking and curated adjacency are immutable for this search scope.
        # Build once: individual roots must not re-sort the full 100k corpus.
        self._ranked = roots
        self._curated_partners = {}
        for pair in tree.collisions:
            self._curated_partners.setdefault(pair["a"], set()).add(pair["b"])
            self._curated_partners.setdefault(pair["b"], set()).add(pair["a"])
        domains = {}
        for concept in roots:
            domains.setdefault(concept.domain_cn, []).append(concept.id)
        per_domain = max(1, self.CAND_CAP // max(1, len(domains)))
        selected = {cid for group in domains.values() for cid in group[:per_domain]}
        self._roots = sorted(selected | {cid for cid in curated if cid in tree.by_id})

    def _cands_for(self, cid: str) -> list[str]:
        """某概念的跨领域候选搭档(标签优先级截断到 CAND_CAP), 懒计算+缓存.

        curated 碰撞涉及的搭档永不截断: 人工精选对必须可达,
        不随规模增长被稀释(9417 规模下 835 个"核心", PR07 曾被挤出 top-600).
        """
        if cid not in self._cands:
            me = self.tree.get(cid)
            pool = [o for o in self._ranked
                    if o.id != cid and o.domain_cn != me.domain_cn]
            if len(pool) <= self.CAND_CAP:
                cands = [o.id for o in pool]
            else:
                cands = [pool[i * len(pool) // self.CAND_CAP].id
                         for i in range(self.CAND_CAP)]
            for other in sorted(self._curated_partners.get(cid, ())):
                if (other not in cands
                        and self.tree.get(other).domain_cn != me.domain_cn):
                    cands.append(other)
            self._cands[cid] = cands
        return self._cands[cid]

    def initial_state(self):
        return ()

    def actions(self, state) -> list:
        if len(state) == 0:
            if self.seed:
                return [self.seed]
            return self._roots
        if len(state) == 1:
            return self._cands_for(state[0])
        return []

    def step(self, state, action):
        return state + (action,)

    def terminal(self, state) -> bool:
        return len(state) == 2

    def reward(self, state) -> float:
        if len(state) != 2:
            return 0.0
        return collision_score(self.tree, state[0], state[1])

    def _best_partner(self, cid: str) -> float:
        if cid not in self._best_cache:
            self._best_cache[cid] = max(
                (collision_score(self.tree, cid, o)
                 for o in self._cands_for(cid)),
                default=0.0)
        return self._best_cache[cid]

    def simulate(self, state, rng, max_depth: int) -> float:
        if len(state) == 0:
            if self.seed:
                return self._best_partner(self.seed)
            # 全局: 懒计算各概念最优搭档的最大值
            return max((self._best_partner(cid)
                        for cid in self._roots), default=0.0)
        if len(state) == 1:
            return self._best_partner(state[0])
        return self.reward(state)


def collide_concepts(tree: KnowledgeTree, seed: str | None = None,
                     top_k: int = 5, iterations: int = 3000,
                     seed_rng: int = 7):
    """知识碰撞: 找与 seed(或全局)最值得碰撞的概念.

    seed: 围绕哪个概念碰撞(中文名/英文名/id), None=全局最优碰撞对.
    返回 [(ConceptA, ConceptB, 碰撞分, curated说明或None)].
    """
    problem = CollisionProblem(tree, seed)
    # Collision search relies on observing curated partners even when a node
    # has hundreds of available actions. Disable narrow progressive widening
    # for this bounded two-ply candidate-ranking task.
    _, root = mcts(problem, iterations=iterations, seed=seed_rng,
                   max_depth=4, widening_k=1000.0, widening_alpha=1.0)
    pairs: list[tuple] = []

    def collect(node):
        if problem.terminal(node.state):
            a, b = node.state
            pairs.append((a, b, node.visits, problem.node_value(node),
                          tree.collision_note(a, b)))
        for ch in node.children:
            collect(ch)

    collect(root)
    # 去重(无序对)后按价值排序
    seen: dict[frozenset, tuple] = {}
    for a, b, v, m, note in pairs:
        key = frozenset((a, b))
        if key not in seen or seen[key][3] < m:
            seen[key] = (a, b, v, m, note)
    ranked = sorted(seen.values(), key=lambda x: (x[3], x[2]),
                    reverse=True)
    return [(tree.get(a), tree.get(b), m, note)
            for a, b, _, m, note in ranked[:top_k]]


def search_concepts(tree: KnowledgeTree, query: str, top_k: int = 5,
                    iterations: int = 2000, seed: int = 7):
    """用 MCTS 在知识树上检索与 query 最相关的 top_k 个概念.

    返回 [(Concept, 访问次数, 价值)] 列表，按价值降序，访问次数打破并列。
    """
    if top_k <= 0:
        return []
    # Scores are computed exactly for every leaf; no incomplete MCTS traversal.
    problem = ConceptSearchProblem(query=query, tree=tree)
    ranked = sorted(tree.concepts,
                    key=lambda c: (-problem._leaf_reward[c.id], c.id))
    return [(c, 0, problem._leaf_reward[c.id]) for c in ranked[:top_k]]

