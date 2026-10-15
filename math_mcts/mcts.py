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

    def iter_actions(self, state):
        """Optional lazy action stream, yielded in caller-defined priority order.

        The default preserves the old list-based interface. Do not use an
        infinite iterator unless the finite search budget is intentional.
        """
        return iter(self.actions(state))

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

    # -- 价值回传方式 --------------------------------------------------
    # "mean": 回传均值, 适合序贯决策(学习路径规划);
    # "max":  回传子树最优值, 适合"找最优叶节点"类搜索(概念检索/知识碰撞),
    #         此时 MCTS 为 UCB 分支限界, 均值回传会稀释父节点价值导致错过最优分支.
    value_op = "mean"

    def action_weight(self, state, action) -> float:
        """Heuristic ranking only. No mathematical truth assertion."""
        return 1.0

    def success_found(self) -> bool:
        """Opt-in early stopping, when a separately checked witness exists."""
        return False

    def node_value(self, node) -> float:
        if node.visits == 0:
            return 0.0
        if self.value_op == "max":
            return node.best
        return node.total / node.visits

    def accumulate(self, node, value: float) -> None:
        node.visits += 1
        if self.value_op == "max":
            if node.best is None or value > node.best:
                node.best = value
        else:
            node.total += value


class _Node:
    __slots__ = ("state", "parent", "action", "children",
                 "untried", "untried_priors", "stream", "stream_exhausted",
                 "visits", "total", "best", "prior", "stats")

    def __init__(self, state, parent=None, action=None, actions=(), prior=1.0, stream=None):
        self.state = state
        self.parent = parent
        self.action = action          # 从 parent 到本节点的动作
        self.children: list["_Node"] = []
        self.untried: list = list(actions)
        self.untried_priors: list[float] = []
        self.stream = stream
        self.stream_exhausted = stream is None
        self.visits = 0
        self.total = 0.0
        self.best = None              # max 回传时的子树最优值
        self.prior = prior
        self.stats = None

    @property
    def mean(self) -> float:
        return self.total / self.visits if self.visits else 0.0

    def uct(self, c: float, problem: "Problem", policy="uct") -> float:
        if policy == "puct":
            q = problem.node_value(self) if self.visits else 0.0
            return q + c * self.prior * math.sqrt(self.parent.visits + 1) / (1 + self.visits)
        if self.visits == 0:
            return float("inf")
        return (problem.node_value(self)
                + c * math.sqrt(math.log(max(1, self.parent.visits)) / self.visits))


def mcts(problem: Problem, iterations: int = 1000,
         exploration: float = 1.414, max_depth: int = 60,
         seed: int | None = None, *, widening_k: float = 2.0,
         widening_alpha: float = 0.5, policy: str = "uct",
         stop_on_success: bool = False, action_mode: str = "eager",
         plateau_patience: int | None = None, min_plateau_iterations: int = 20):
    """Bounded MCTS with progressive widening for very wide action spaces.

    The number of expanded children grows as ceil(k * (visits+1)**alpha).
    This allows the search to descend before all root actions are expanded.
    "mean" problems use the robust-child extraction policy; "max" problems
    extract the child with greatest backed-up value. Neither policy is a
    proof of global optimality; rollout values may be estimates.
    """
    if action_mode not in {"eager", "stream"}:
        raise ValueError("action_mode must be eager or stream")
    if action_mode == "stream" and policy != "uct":
        raise ValueError("Streamed actions cannot use globally normalized PUCT priors")
    if plateau_patience is not None and (
        type(plateau_patience) is not int or plateau_patience < 1
    ):
        raise ValueError("plateau_patience must be a positive integer or None")
    if type(min_plateau_iterations) is not int or min_plateau_iterations < 1:
        raise ValueError("min_plateau_iterations must be a positive integer")
    if policy not in {"uct", "puct"}:
        raise ValueError("policy must be uct or puct")
    if not isinstance(iterations, int) or iterations < 0:
        raise ValueError("iterations must be a nonnegative integer")
    if max_depth < 0 or exploration < 0 or widening_k <= 0 or not 0 < widening_alpha <= 1:
        raise ValueError("Invalid search/depth/widening parameters")
    rng = random.Random(seed)
    initial = problem.initial_state()
    def new_node(state, parent=None, action=None, prior=1.0):
        if action_mode == "stream":
            return _Node(state, parent=parent, action=action, prior=prior,
                         stream=iter(problem.iter_actions(state)))
        return _Node(state, parent=parent, action=action, prior=prior,
                     actions=problem.actions(state))

    root = new_node(initial)

    def prepare_priors(node):
        if policy != "puct" or not node.untried:
            return
        weights = [float(problem.action_weight(node.state, a)) for a in node.untried]
        if any(not math.isfinite(w) or w < 0 for w in weights):
            raise ValueError("action_weight must be finite and nonnegative")
        if not any(weights):
            weights = [1.0] * len(weights)
        total = sum(weights)
        if not math.isfinite(total):
            raise ValueError("Action weight sum must be finite")
        paired = list(zip(node.untried, (w / total for w in weights)))
        rng.shuffle(paired)  # seed-controlled unbiased ties
        paired.sort(key=lambda pair: pair[1])
        node.untried = [action for action, _ in paired]
        node.untried_priors = [prior for _, prior in paired]

    prepare_priors(root)
    stats = {"requested_iterations": iterations, "simulations": 0,
             "created_nodes": 1, "guided_expansions": 0,
             "policy": policy, "early_stop": False,
             "action_mode": action_mode, "yielded_actions": 0,
             "stream_exhausted_nodes": 0, "plateau_stop": False}
    best_observed = float("-inf")
    stale_simulations = 0
    for _ in range(iterations):
        if stop_on_success and problem.success_found():
            stats["early_stop"] = True
            break
        node, depth = root, 0
        # Select/expand at every depth. A large untried root no longer
        # prevents deeper exploration under a finite iteration budget.
        while depth < max_depth and not problem.terminal(node.state):
            allowance = max(1, math.ceil(widening_k * (node.visits + 1) ** widening_alpha))
            if (node.untried or not node.stream_exhausted) and len(node.children) < allowance:
                if action_mode == "stream":
                    try:
                        action = next(node.stream)
                    except StopIteration:
                        node.stream_exhausted = True
                        stats["stream_exhausted_nodes"] += 1
                        if not node.children:
                            break
                        node = max(node.children,
                                   key=lambda ch: ch.uct(exploration, problem, policy))
                        depth += 1
                        continue
                    stats["yielded_actions"] += 1
                    prior = 1.0
                elif policy == "puct":
                if policy == "puct":
                    # Priors are normalized ONCE for the complete action set,
                    # not renormalized after each widening expansion.
                    action = node.untried.pop()
                    prior = node.untried_priors.pop()
                    stats["guided_expansions"] += 1
                else:
                    prior = 1.0
                    action = node.untried.pop(rng.randrange(len(node.untried)))
                child_state = problem.step(node.state, action)
                child = new_node(child_state, parent=node, action=action, prior=prior)
                prepare_priors(child)
                stats["created_nodes"] += 1
                node.children.append(child)
                node = child
                depth += 1
                break
            if not node.children:
                break
            node = max(node.children,
                       key=lambda ch: ch.uct(exploration, problem, policy))
            depth += 1
        # Simulated value is not necessarily the value of the expanded node.
        value = problem.simulate(node.state, rng, max_depth - depth)
        if not math.isfinite(value):
            raise ValueError("Simulation reward must be finite")
        stats["simulations"] += 1
        if value > best_observed:
            best_observed = value
            stale_simulations = 0
        else:
            stale_simulations += 1
        while node is not None:
            problem.accumulate(node, value)
            node = node.parent
        # An optional *heuristic* resource controller. Sparse-reward
        # problems can plateau before a solution exists; never interpret
        # this as exhaustion, impossibility or proof of optimality.
        if (plateau_patience is not None
            and stats["simulations"] >= min_plateau_iterations
            and stale_simulations >= plateau_patience):
            stats["plateau_stop"] = True
            break

    actions_seq: list = []
    node = root
    while node.children and len(actions_seq) < max_depth:
        if problem.value_op == "max":
            node = max(node.children,
                       key=lambda ch: (problem.node_value(ch), ch.visits))
        else:
            node = max(node.children,
                       key=lambda ch: (ch.visits, problem.node_value(ch)))
        actions_seq.append(node.action)
        if problem.terminal(node.state):
            break
    root.stats = stats
    return actions_seq, root
