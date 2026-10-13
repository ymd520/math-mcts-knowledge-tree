"""蒙特卡洛树搜索 (MCTS) 引擎.

标准四步循环: 选择(UCB1) -> 扩展 -> 模拟(随机 rollout) -> 回传.
通过 ``Problem`` 接口与具体任务解耦, 同一个引擎可驱动
"学习路径规划"与"概念检索"两种搜索.
"""
from __future__ import annotations

import math
import random


class Problem:
    """搜索问题接口(鸭子类型, 子类按需实现)."""

    def initial_state(self):
        raise NotImplementedError

    def actions(self, state) -> list:
        """state 下可执行的动作列表(空列表表示无后继)."""
        raise NotImplementedError

    def step(self, state, action):
        raise NotImplementedError

    def terminal(self, state) -> bool:
        raise NotImplementedError

    def reward(self, state) -> float:
        """终局状态的回报, 越大越好."""
        raise NotImplementedError

    def simulate(self, state, rng, max_depth: int) -> float:
        """模拟步: 从 state 出发估计回报. 默认随机 rollout.

        子类可覆盖: 若状态空间完全已知且叶节点评分廉价,
        可用精确求值代替随机模拟(见 ConceptSearchProblem).
        """
        depth = 0
        while not self.terminal(state) and depth < max_depth:
            acts = self.actions(state)
            if not acts:
                break
            state = self.step(state, acts[rng.randrange(len(acts))])
            depth += 1
        return self.reward(state)


class _Node:
    __slots__ = ("state", "parent", "action", "children",
                 "untried", "visits", "total")

    def __init__(self, state, parent=None, action=None, actions=()):
        self.state = state
        self.parent = parent
        self.action = action          # 从 parent 到本节点的动作
        self.children: list["_Node"] = []
        self.untried: list = list(actions)
        self.visits = 0
        self.total = 0.0

    @property
    def mean(self) -> float:
        return self.total / self.visits if self.visits else 0.0

    def uct(self, c: float) -> float:
        if self.visits == 0:
            return float("inf")
        return (self.mean
                + c * math.sqrt(math.log(self.parent.visits) / self.visits))


def mcts(problem: Problem, iterations: int = 1000,
         exploration: float = 1.414, max_depth: int = 60,
         seed: int | None = None):
    """运行 MCTS, 返回 (最优动作序列, 根节点).

    最优动作序列按"访问次数最多子节点"(robust child)逐层选取,
    这是 MCTS 实践中的标准做法.
    """
    rng = random.Random(seed)
    root = _Node(problem.initial_state(), actions=problem.actions(
        problem.initial_state()))

    for _ in range(iterations):
        node, depth = root, 0
        # 1) 选择: 沿 UCB1 下行到可扩展/终局节点
        while node.untried == [] and node.children and \
                not problem.terminal(node.state) and depth < max_depth:
            node = max(node.children, key=lambda ch: ch.uct(exploration))
            depth += 1
        # 2) 扩展: 尝试一个未试过的动作
        if node.untried and not problem.terminal(node.state) \
                and depth < max_depth:
            action = node.untried.pop(rng.randrange(len(node.untried)))
            child_state = problem.step(node.state, action)
            child = _Node(child_state, parent=node, action=action,
                          actions=problem.actions(child_state))
            node.children.append(child)
            node = child
            depth += 1
        # 3) 模拟: 调用问题的 simulate 钩子(默认随机 rollout)
        value = problem.simulate(node.state, rng, max_depth - depth)
        # 4) 回传
        while node is not None:
            node.visits += 1
            node.total += value
            node = node.parent

    # 提取最优动作序列(每层选访问次数最多的子节点)
    actions_seq: list = []
    node = root
    while node.children:
        node = max(node.children, key=lambda ch: (ch.visits, ch.mean))
        actions_seq.append(node.action)
        if problem.terminal(node.state):
            break
    return actions_seq, root
