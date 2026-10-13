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

    def initial_state(self):
        return self.known

    def actions(self, state) -> list:
        learned = set(state)
        cands = [c.id for c in self.tree.concepts
                 if c.id not in learned and set(c.prereq) <= learned]
        return sorted(cands)  # 排序保证可复现

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
    """规划学习目标概念的最优路径, 返回有序的 Concept 列表.

    known: 已掌握的概念 id 列表, 规划从这些概念之后开始.
    """
    concept = tree.find(target)
    known_ids = [k for k in known if k in tree.by_id]
    problem = LearningPathProblem(tree, concept.id, max_steps, known_ids)
    seq, _ = mcts(problem, iterations=iterations, seed=seed)
    # 兜底: 若 MCTS 未走到目标, 用拓扑闭包补全
    learned = list(problem.initial_state()) + list(seq)
    if concept.id not in learned:
        for pid in tree.prereq_closure(concept.id):
            if pid not in learned:
                learned.append(pid)
        learned.append(concept.id)
    return [tree.get(cid) for cid in learned]


def export_path_markdown(path: list[Concept]) -> str:
    """把学习路径导出为 Markdown 学习计划."""
    target = path[-1]
    lines = [f"# 学习计划: {target.cn}({target.en})",
             "",
             f"共 {len(path)} 步, 由 MCTS 在知识前置依赖图上规划.",
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
    直接返回该子树下所有概念的最大相关度. 此时 MCTS 等价于
    UCB 探索引导的最优分支限界搜索, 必收敛到全局最相关概念,
    且访问次数真实反映各分支的价值(可用于可视化).
    """

    def __init__(self, tree: KnowledgeTree, query: str):
        self.tree = tree
        self.query = query
        self.qtok = Counter(_tokenize(query))
        self.qtotal = sum(self.qtok.values()) or 1

    def simulate(self, state, rng, max_depth: int) -> float:
        best = 0.0
        stack = [state]
        while stack:
            s = stack.pop()
            if self.tree.is_concept_leaf(s):
                r = self.reward(s)
                if r > best:
                    best = r
            else:
                stack.extend(self.tree.hierarchy_children(s))
        return best

    def initial_state(self):
        return ()

    def actions(self, state) -> list:
        return self.tree.hierarchy_children(state)

    def step(self, state, action):
        return action

    def terminal(self, state) -> bool:
        return self.tree.is_concept_leaf(state)

    def reward(self, state) -> float:
        if not self.tree.is_concept_leaf(state):
            return 0.0
        c = self.tree.leaf_concept(state)
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


def search_concepts(tree: KnowledgeTree, query: str, top_k: int = 5,
                    iterations: int = 2000, seed: int = 7):
    """用 MCTS 在知识树上检索与 query 最相关的 top_k 个概念.

    返回 [(Concept, 访问次数, 平均回报)] 列表, 按访问次数降序.
    """
    problem = ConceptSearchProblem(query=query, tree=tree)
    _, root = mcts(problem, iterations=iterations, seed=seed,
                   max_depth=6)

    leaves: list[tuple] = []

    def collect(node):
        if tree.is_concept_leaf(node.state):
            leaves.append((node.state, node.visits, node.mean))
        for ch in node.children:
            collect(ch)

    collect(root)
    # 按 MCTS 估计的平均回报(价值)排序 —— 这是 MCTS 返回最优解的标准做法;
    # 访问次数仅作并列时的 tie-break.
    leaves.sort(key=lambda x: (x[2], x[1]), reverse=True)
    return [(tree.leaf_concept(s), v, m) for s, v, m in leaves[:top_k]]
