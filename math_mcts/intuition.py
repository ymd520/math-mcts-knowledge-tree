"""直觉先验：把数学结构直觉作为 MCTS 的探索先验（PUCT prior）。

来源：2026-10-26 直觉先验原型（51 个经典核心概念的手写签名与规则评分，
藏答案测试 recall@10 88%、中位名次 2）。签名在原型层验证后移入此处，
仍属“待专家复核的派生层”，不是精选库的正式收录，更不是证明。

接入方式（刻意保守）：
  - 旧 ``collide_concepts`` 的终局评分仍是 ``collision_score``，
    curated 对 AN21 x PR07 在旧接口下仍排第一（见 tests/test_mcts.py）。
    （2026-10-31 等概率落地改了旧接口的候选生成：种子模式改为
    全量评分、全局模式改为均匀采样；评分函数本身未动。）
  - 新接口 ``collide_with_intuition`` 只改探索顺序：用 MCTS 的 PUCT 策略，
    ``IntuitionCollisionProblem.action_weight`` 返回直觉分作先验；
    直觉分高只意味着“值得先试”，不改变终局评分，不等于定理成立。
  - 适用范围：先验只覆盖 SIGNATURES 里的 51 个概念；未签名概念一律给
    下限权重 0.05（仍可被探索，不被排除），不假装对它们有直觉。
  - 跨域门：CollisionProblem 本身只允许不同领域/分支的搭档，
    因此同领域高分对（如导数 x 定积分）不会进入碰撞结果；
    直觉分用于碰撞时，跨域是硬约束，不是可加分项之外的软偏好。
  - 量纲与规则：见 ``intuition_rules`` 返回的分项；每个高分都可审计
    是哪条规则触发的，不接受无法解释的黑箱分。

签名格式（与原型一致）：
  id: (main_type, role, applies_to, produces, invariants, patterns,
       dual, discrete, finite)
  main_type / applies_to / produces 共用对象类型词表；dual 只填真正的
  对偶/逆运算，不填 curated 搭档。
"""
from __future__ import annotations

from collections import Counter

from .mcts import mcts
from .search import CollisionProblem

SIGNATURES = {
    "AN21": ("function", "operator", {"function", "signal", "distribution"}, {"spectrum", "function"}, {"linearity", "orthogonality"}, {"transform", "spectral", "duality"}, None, "continuous", "infinite"),
    "PR07": ("distribution", "object", {"random_variable", "distribution"}, {"number"}, {"linearity"}, {"limit", "sampling"}, None, "both", "both"),
    "PR32": ("distribution", "operator", {"distribution", "random_variable"}, {"function"}, {"linearity"}, {"transform", "duality"}, None, "both", "both"),
    "AN20": ("function", "operator", {"function", "signal"}, {"sequence", "function"}, {"orthogonality", "linearity"}, {"transform", "spectral", "orthogonality"}, None, "continuous", "infinite"),
    "AL11": ("vector", "structure", {"vector", "function"}, {"number", "projection"}, {"orthogonality", "linearity"}, {"orthogonality", "spectral"}, None, "both", "both"),
    "AN06": ("function", "operator", {"function", "distribution"}, {"number"}, {"linearity"}, {"limit"}, "AN03", "continuous", "both"),
    "PR06": ("distribution", "object", {"random_variable"}, {"number"}, {"measure"}, {"limit"}, None, "continuous", "infinite"),
    "AN03": ("function", "operator", {"function"}, {"function"}, {"linearity"}, {"limit", "variational"}, "AN06", "continuous", "both"),
    "CA06": ("function", "method", {"function"}, {"sequence", "minimizer"}, {"convexity"}, {"variational", "iteration"}, None, "both", "both"),
    "B7A0140": ("function", "object", {"function"}, {"number"}, {"convexity"}, {"variational"}, None, "both", "both"),
    "CA07": ("function", "method", {"function", "equation"}, {"sequence", "root"}, set(), {"iteration", "fixed_point"}, None, "both", "both"),
    "AN161": ("space", "theorem", {"space", "function"}, {"fixed_point"}, {"completeness"}, {"fixed_point", "iteration"}, None, "both", "both"),
    "LV20530": ("function", "method", {"function", "space"}, {"sequence", "fixed_point"}, set(), {"fixed_point", "iteration"}, None, "both", "both"),
    "AL30": ("matrix", "operator", {"matrix", "data"}, {"vector", "matrix"}, {"orthogonality", "spectral"}, {"spectral", "duality"}, None, "both", "both"),
    "PR40": ("data", "method", {"matrix", "data", "distribution"}, {"vector", "data"}, {"orthogonality", "variance"}, {"spectral", "variational"}, None, "both", "finite"),
    "PR15": ("process", "object", {"distribution", "state"}, {"distribution", "process"}, {"stationarity"}, {"limit", "iteration"}, None, "discrete", "both"),
    "AL05": ("matrix", "object", {"vector", "distribution"}, {"vector", "matrix", "distribution"}, {"linearity"}, {"spectral"}, None, "both", "both"),
    "CA19": ("graph", "method", {"graph", "matrix", "distribution"}, {"vector", "distribution"}, {"stationarity"}, {"spectral", "fixed_point", "iteration"}, None, "discrete", "finite"),
    "LV32610": ("matrix", "theorem", {"matrix"}, {"vector", "eigenvalue"}, {"positivity", "spectral"}, {"spectral", "fixed_point"}, None, "both", "finite"),
    "LV34231": ("operator", "theorem", {"operator", "process"}, {"semigroup", "generator"}, {"contractivity"}, {"spectral", "limit"}, None, "continuous", "infinite"),
    "GE97": ("space", "theorem", {"space", "function"}, {"fixed_point"}, {"topology", "continuity"}, {"fixed_point", "compactness"}, None, "both", "finite"),
    "DM160": ("game", "object", {"game", "strategy"}, {"equilibrium", "fixed_point"}, set(), {"fixed_point", "variational"}, None, "both", "finite"),
    "LV33967": ("game", "theorem", {"game", "equilibrium"}, {"complexity"}, set(), {"fixed_point", "counting"}, None, "both", "finite"),
    "LV34831": ("space", "theorem", {"space", "correspondence"}, {"fixed_point"}, {"convexity", "continuity"}, {"fixed_point", "compactness"}, None, "both", "both"),
    "AN17": ("equation", "object", {"function", "system"}, {"function", "oscillation"}, {"linearity"}, {"spectral", "variational"}, None, "continuous", "both"),
    "AL10": ("matrix", "object", {"matrix", "operator"}, {"number", "vector"}, {"spectral", "linearity"}, {"spectral"}, None, "both", "both"),
    "AL04": ("vector", "object", {"space"}, {"vector"}, {"linearity"}, set(), None, "both", "both"),
    "GE04": ("space", "structure", {"space", "vector", "geometry"}, {"vector", "number"}, {"linearity"}, set(), None, "both", "both"),
    "BS11": ("logic", "structure", {"statement", "function", "set"}, {"statement"}, set(), set(), None, "both", "both"),
    "AN01": ("function", "object", {"function", "sequence"}, {"number"}, {"continuity"}, {"limit"}, None, "both", "infinite"),
    "DM06": ("graph", "object", {"graph"}, {"graph"}, {"acyclicity"}, {"optimal_substructure"}, None, "discrete", "finite"),
    "CA11": ("problem", "method", {"graph", "sequence", "problem"}, {"sequence", "number"}, {"optimal_substructure"}, {"optimal_substructure", "iteration"}, None, "discrete", "finite"),
    "DM07": ("graph", "problem", {"graph"}, {"path", "number"}, {"optimal_substructure"}, {"optimal_substructure"}, None, "discrete", "finite"),
    "CA12": ("distribution", "method", {"distribution", "integral", "problem"}, {"number", "estimate"}, set(), {"sampling", "limit"}, None, "both", "both"),
    "PR09": ("distribution", "theorem", {"random_variable", "distribution"}, {"limit", "number"}, set(), {"limit", "sampling"}, None, "both", "infinite"),
    "PR71": ("distribution", "theorem", {"random_variable", "distribution"}, {"limit", "number"}, set(), {"limit", "sampling"}, None, "both", "infinite"),
    "CA29": ("integral", "method", {"integral", "distribution", "function"}, {"number"}, set(), {"sampling", "limit"}, None, "both", "both"),
    "PR169": ("distribution", "object", {"distribution", "code"}, {"number"}, {"information"}, {"variational", "duality"}, None, "both", "both"),
    "CA34": ("code", "method", {"distribution", "code", "data"}, {"code"}, {"information", "optimal_substructure"}, {"optimal_substructure", "variational"}, None, "discrete", "finite"),
    "CA114": ("distribution", "object", {"distribution", "model"}, {"number"}, {"information"}, {"variational", "duality"}, None, "both", "both"),
    "DM01": ("counting", "method", {"set", "sequence", "distribution"}, {"number"}, {"counting"}, {"counting"}, None, "discrete", "finite"),
    "PR05": ("distribution", "object", {"random_variable"}, {"number"}, {"counting"}, {"counting", "sampling"}, None, "discrete", "both"),
    "AL13": ("structure", "object", {"set", "symmetry", "space"}, {"group"}, {"symmetry", "closure"}, set(), None, "both", "both"),
    "GE10": ("space", "object", {"space", "topology"}, {"space"}, {"topology", "continuity"}, {"duality"}, None, "both", "both"),
    "BS07": ("set", "structure", {"set", "group"}, {"partition", "quotient"}, {"symmetry"}, set(), None, "both", "both"),
    "AN19": ("function", "method", {"function"}, {"sequence", "function"}, {"linearity"}, {"limit", "transform"}, None, "continuous", "infinite"),
    "CA03": ("integral", "method", {"function", "integral"}, {"number"}, set(), {"limit", "sampling"}, None, "both", "both"),
    "DM11": ("problem", "method", {"algorithm", "problem", "recursion"}, {"number", "complexity"}, set(), {"counting"}, None, "both", "both"),
    "CA10": ("problem", "method", {"problem", "sequence"}, {"algorithm"}, {"optimal_substructure"}, {"optimal_substructure", "counting"}, None, "both", "both"),
    "CA15": ("problem", "method", {"game", "problem", "distribution"}, {"action", "estimate"}, set(), {"sampling", "iteration"}, None, "both", "both"),
    "PR02": ("distribution", "object", {"distribution", "event"}, {"number", "distribution"}, set(), {"sampling", "limit"}, None, "both", "both"),
}

_INV_COUNTER = Counter()
_PAT_COUNTER = Counter()
for _sig in SIGNATURES.values():
    for _inv in _sig[4]:
        _INV_COUNTER[_inv] += 1
    for _pat in _sig[5]:
        _PAT_COUNTER[_pat] += 1

_FLOOR = 0.05


def intuition_rules(tree, a: str, b: str):
    """返回 (总分, 分项字典)；任一方未签名则返回 (None, None)。

    规则权重固定，不拟合；分项用于审计每一次高分是哪条规则触发的。
    """
    if a not in SIGNATURES or b not in SIGNATURES:
        return None, None
    (ma, ra, aa, pa, ia, pata, da, disa, fina) = SIGNATURES[a]
    (mb, rb, ab, pb, ib, patb, db, disb, finb) = SIGNATURES[b]
    rules = {}
    if (ra in {"method", "operator", "theorem"} and mb in aa) or \
       (rb in {"method", "operator", "theorem"} and ma in ab):
        rules["tool_object"] = 3.0
    if (pa & ab) or (pb & aa):
        rules["composition"] = 2.0
    if (da == b) or (db == a):
        rules["duality"] = 3.0
    shared_inv = ia & ib
    if shared_inv:
        rules["shared_invariant"] = round(min(3.0, sum(
            0.5 if _INV_COUNTER[inv] > 10 else 1.5 for inv in shared_inv)), 3)
    shared_pat = pata & patb
    if shared_pat:
        rules["same_pattern"] = round(min(2.0, sum(
            0.5 if _PAT_COUNTER[pat] > 10 else 1.0 for pat in shared_pat)), 3)
    if ma == mb:
        rules["same_main_type"] = 1.0
    ca, cb = tree.get(a), tree.get(b)
    if ca.domain_cn != cb.domain_cn:
        rules["cross_domain"] = 0.5
    if (disa != "both" and disb != "both" and disa != disb) or \
       (fina != "both" and finb != "both" and fina != finb):
        rules["scale_mismatch"] = -1.0
    return round(sum(rules.values()), 3), rules


def intuition_score(tree, a: str, b: str):
    """直觉先验分；任一方未签名返回 None（不假装有直觉）。"""
    score, _ = intuition_rules(tree, a, b)
    return score


class IntuitionCollisionProblem(CollisionProblem):
    """直觉先验版知识碰撞：终局评分继承 CollisionProblem，只改先验。

    action_weight 是 PUCT 先验，不是终局回报：根层权重取该概念对所有
    跨域已签名搭档的最高直觉分（它的“直觉潜力”），第二层权重取该对的
    直觉分；未签名一律给下限权重，仍可被探索。
    """

    def __init__(self, tree, seed=None, *, diversity_axis="domain",
                 seed_rng=7):
        super().__init__(tree, seed, diversity_axis=diversity_axis,
                         seed_rng=seed_rng)
        self._potential_cache = {}

    def _potential(self, cid: str) -> float:
        if cid not in self._potential_cache:
            if cid not in SIGNATURES:
                self._potential_cache[cid] = _FLOOR
            else:
                me = self.tree.get(cid)
                best = 0.0
                for other in SIGNATURES:
                    if other == cid:
                        continue
                    oc = self.tree.get(other)
                    if not self._different_group(oc, me):
                        continue
                    s = intuition_score(self.tree, cid, other)
                    if s is not None and s > best:
                        best = s
                self._potential_cache[cid] = max(best, 0.0) + _FLOOR
        return self._potential_cache[cid]

    def action_weight(self, state, action) -> float:
        if len(state) == 0:
            return self._potential(action)
        if len(state) == 1:
            s = intuition_score(self.tree, state[0], action)
            if s is None:
                return _FLOOR
            return max(s, 0.0) + _FLOOR
        return _FLOOR


def collide_with_intuition(tree, seed=None, top_k=5, iterations=1000,
                           seed_rng=7, *, diversity_axis="domain",
                           widening_k=2.0, widening_alpha=0.5):
    """直觉先验版知识碰撞（PUCT 先验 + 旧终局评分）。

    返回与 collide_concepts 相同的 4 元组
    [(ConceptA, ConceptB, 碰撞分, curated 说明或 None)]，便于对照；
    某对的直觉分与分项另用 intuition_score / intuition_rules 查询。
    widening 默认取 MCTS 默认值（2.0 / 0.5），而不是旧 collide 的
    1000/1.0：先验只有在预算受限、不能把全部候选都展开时才真正起
    指导作用；把全部候选都展开就等于先验白给。
    """
    problem = IntuitionCollisionProblem(tree, seed, diversity_axis=diversity_axis,
                                      seed_rng=seed_rng)
    _, root = mcts(problem, iterations=iterations, seed=seed_rng,
                   max_depth=4, policy="puct",
                   widening_k=widening_k, widening_alpha=widening_alpha)
    pairs = []

    def collect(node):
        if problem.terminal(node.state):
            a, b = node.state
            pairs.append((a, b, node.visits, problem.node_value(node),
                          tree.collision_note(a, b)))
        for ch in node.children:
            collect(ch)

    collect(root)
    seen = {}
    for a, b, v, m, note in pairs:
        key = frozenset((a, b))
        if key not in seen or seen[key][3] < m:
            seen[key] = (a, b, v, m, note)
    ranked = sorted(seen.values(), key=lambda x: (x[3], x[2]), reverse=True)
    return [(tree.get(a), tree.get(b), m, note)
            for a, b, _, m, note in ranked[:top_k]]
