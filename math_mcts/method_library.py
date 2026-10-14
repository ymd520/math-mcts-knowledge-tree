"""Explicit mathematical *research actions*, not a theorem or proof library.

Operators are editorially authored templates, not claims of originality.
Recommendation is deterministic lexical retrieval; each application still needs
a theorem-specific type check, mathematical justification, and counterexample
attack. MCTS can consume these *proposals* as possible actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

@dataclass(frozen=True)
class Operator:
    key: str
    name: str
    domains: tuple[str, ...]
    triggers: tuple[str, ...]
    requires: str
    action: str
    proof_obligation: str
    failure_test: str
    category: str

# English and Chinese triggers are deliberately included. Keywords are a
# retrieval lead, never an assertion that the method is applicable.
_DATA = [
    ("fourier_switch", "Fourier representation / 傅里叶转换", "harmonic algebra probability", "fourier 傅里叶 卷积 convolution representation",
     "A compatible group or transform domain and stated normalizations",
     "Express the operation in the dual/frequency representation",
     "Derive inversion, scaling and representation conventions",
     "Try a noncommutative group where scalar Fourier coefficients fail", "change_representation"),
    ("duality", "Primal-dual formulation / 对偶化", "optimization analysis algebra", "dual 对偶 上界 下界 bound certificate",
     "Specify primal variables, constraints and objective",
     "Construct a dual feasible certificate or exact dual problem",
     "Prove weak duality; justify strong duality if used",
     "Test infeasible or non-convex cases", "change_representation"),
    ("linearization", "Linearization / 线性化", "analysis optimization geometry", "linear 线性化 局部 perturbation",
     "A precise base point and regularity hypotheses",
     "Take a first variation or tangent model",
     "Bound the remainder and identify the valid neighborhood",
     "Test singular points and large perturbations", "change_representation"),
    ("quotient", "Quotient reduction / 商结构", "algebra topology combinatorics", "quotient 商群 商空间 kernel 核",
     "Normal subgroup or equivalence relation compatible with operations",
     "Factor the problem through a quotient structure",
     "Check quotient well-definedness and loss of information",
     "Test a non-normal subgroup", "change_structure"),
    ("lift", "Lifting / 提升", "algebra geometry topology", "lift 提升 覆盖 covering extension",
     "A map and target property that can be lifted",
     "Construct a lift to a larger or covering structure",
     "Check obstruction and descent of the resulting solution",
     "Test failure of compatibility around a cycle", "change_structure"),
    ("tensor_product", "Product or tensor / 乘积张量化", "algebra analysis probability", "tensor 张量 直积 product",
     "Compatible objects with explicitly stated product law",
     "Form a product model and test factorization",
     "Prove how invariants, norm and constants scale",
     "Test coupled interactions that destroy factorization", "change_structure"),
    ("symmetry_reduction", "Symmetry orbit reduction / 对称性约化", "algebra combinatorics geometry", "symmetry 对称 轨道 orbit action",
     "A proved symmetry action preserving the objective",
     "Pass to orbit representatives or invariant variables",
     "Prove equivariance and completeness of reduced cases",
     "Test stabilizers with different sizes", "change_structure"),
    ("invariant_design", "Construct an invariant / 不变量构造", "algebra combinatorics topology", "invariant 不变量 守恒 obstruction",
     "A set of transformations whose invariant is sought",
     "Propose a quantity conserved under allowed transformations",
     "Check invariance for every generator and boundary case",
     "Find an allowed move that changes the candidate invariant", "invent_tool"),
    ("extremal_witness", "Extremal witness / 极值见证", "combinatorics analysis optimization", "extremal 极值 最优 maximal",
     "A defined admissible set and attainment or compactness argument",
     "Choose an extremizer and perturb it",
     "Prove existence or use a maximizing sequence with error control",
     "Test noncompact spaces without maximizers", "proof_strategy"),
    ("pigeonhole", "Pigeonhole/counting / 抽屉计数", "combinatorics number_theory", "pigeonhole 抽屉 计数 counting",
     "A finite set partition with exact sizes",
     "Double count incidences or force a crowded cell",
     "Check overlap, injectivity and equality cases",
     "Test a non-disjoint partition", "proof_strategy"),
    ("probabilistic_method", "Probabilistic construction / 概率法", "combinatorics probability", "random 随机 概率 expectation",
     "A finite or measurable random construction and integrability",
     "Select a distribution and bound the expected defects",
     "Translate positive probability into an actual existence statement",
     "Test independence assumptions and rare-event tails", "proof_strategy"),
    ("local_lemma", "Lovasz local lemma / 局部引理", "probability combinatorics", "local lemma 局部引理 dependency",
     "A finite bad-event dependency graph",
     "Control probabilities against dependencies",
     "Verify the exact asymmetric or symmetric lemma criterion",
     "Test hidden dependencies", "proof_strategy"),
    ("spectral_bound", "Spectral relaxation / 谱界", "analysis algebra combinatorics", "spectral 谱 特征值 eigenvalue norm",
     "A well-defined operator and correct inner product",
     "Relate an extremal parameter to spectral data",
     "Justify self-adjointness or use singular values as appropriate",
     "Test nonnormal operators with complex eigenvalues", "bound"),
    ("energy_method", "Energy method / 能量法", "analysis geometry probability", "energy 能量 距离 potential",
     "A nonnegative energy or monotone functional",
     "Compare its derivative or increments to dissipation",
     "Establish coercivity and boundary control",
     "Test zero-energy nontrivial states", "bound"),
    ("convex_relaxation", "Convex relaxation / 凸松弛", "optimization combinatorics", "convex 凸 松弛 relaxation",
     "An original feasible set and a provable enclosing convex set",
     "Optimize over the relaxation to get a certified bound",
     "Check inequality direction and rounding gap",
     "Test fractional extremizers incompatible with discrete data", "bound"),
    ("stability", "Stability from near equality / 稳定性", "analysis combinatorics geometry", "stability 稳定性 近等号 gap",
     "A sharp inequality and an identified equality family",
     "Relate deficit to distance from the equality set",
     "Prove quantitative error modulus and its regime",
     "Find near extremizers far from purported equality cases", "bound"),
    ("compactness", "Compactness extraction / 紧性", "analysis topology", "compact 紧性 subsequence 子序列",
     "A family with the right precompactness bounds",
     "Extract a convergent subnet or subsequence",
     "Pass constraints to the limit under valid topology",
     "Test lack of tightness or escape to infinity", "local_to_global"),
    ("regularity_bootstrap", "Regularity bootstrap / 正则性提升", "analysis pde geometry", "regularity 正则性 smooth 微分",
     "A valid weak solution and an estimate at a lower regularity",
     "Iterate estimates to gain control",
     "Track constants, domains and boundary conditions",
     "Test critical exponents or rough coefficients", "local_to_global"),
    ("induction", "Induction or minimal counterexample / 归纳", "algebra combinatorics number_theory", "induction 归纳 minimal 最小反例",
     "A well-founded order with a valid base case",
     "Reduce a putative counterexample to smaller complexity",
     "Prove reduction preserves all premises",
     "Test an infinite descending chain", "proof_strategy"),
    ("contradiction", "Contradiction / 反证", "logic algebra analysis", "contradiction 反证 absurd",
     "A precisely negated mathematical statement",
     "Assume its negation and deduce a formal inconsistency",
     "Preserve quantifier order and constructive/classical status",
     "Attack misuse of negation of forall/exists", "proof_strategy"),
    ("counterexample_search", "Counterexample family search / 反例族", "logic combinatorics algebra", "counterexample 反例 conjecture 猜想",
     "A falsifiable statement with explicit quantifiers",
     "Enumerate small models and structured boundary families",
     "Independently evaluate all premises and the conclusion",
     "Test false positives caused by numerical tolerance", "falsification"),
    ("finite_field", "Finite-field specialization / 有限域特化", "algebra number_theory combinatorics", "finite field 有限域 素数域",
     "A statement sensible over an explicitly chosen field",
     "Analyze small fields and vary the characteristic",
     "Check field-size restrictions and characteristic-dependent steps",
     "Test characteristic two and very small fields", "falsification"),
    ("abelian_nonabelian", "Commutativity stress test / 非交换攻击", "algebra harmonic", "noncommutative 非交换 群 group",
     "A result involving products or Fourier operations",
     "Test abelian, dihedral and other nonabelian groups",
     "Track multiplication order and representation dimensions",
     "Find the first commutation swap used without justification", "falsification"),
    ("dimensional", "Dimension/rank obstruction / 维数秩障碍", "algebra geometry", "rank 秩 维数 dimension",
     "A finite-dimensional representation or well-defined dimension theory",
     "Compare parameter dimension and constraint rank",
     "Justify rank semicontinuity and genericity claims",
     "Test singular strata and dependent constraints", "falsification"),
    ("computational_certificate", "Exact computational certificate / 精确计算证书", "computation algebra combinatorics", "compute 计算 证书 exact 验证",
     "A finite decidable search space or exact arithmetic representation",
     "Generate and independently replay a minimal witness",
     "Include code version, inputs and integer/rational checks",
     "Recompute without floating-point comparisons", "verification"),
    ("proof_assistant", "Formal kernel verification / 内核验证", "logic computation", "lean 形式化 proof 证明",
     "A precise formal statement in a trusted kernel",
     "Encode the candidate proof and run the kernel",
     "Audit axioms and equivalence to the informal claim",
     "Try to prove a subtly weakened statement instead", "verification"),
    ("transfer_principle", "Transfer principle / 转移原理", "algebra analysis combinatorics", "transfer 转移 推广 一般化",
     "A map preserving the properties under study",
     "Transfer an estimate or construction across structures",
     "Prove mapping assumptions and exact transferred constants",
     "Test loss of surjectivity/injectivity", "invent_tool"),
    ("scale_normalization", "Scaling normalization / 缩放归一", "analysis optimization algebra", "scaling 缩放 normalization 齐次",
     "A genuine scaling symmetry or homogeneity law",
     "Normalize parameters and isolate dimensionless invariants",
     "Check all terms transform consistently under scaling",
     "Test zero and degenerate cases", "change_representation"),
    ("perturbative_oscillation", "Oscillatory cancellation / 振荡抵消", "analysis harmonic", "oscillation 振荡 cancellation 相位",
     "A signed or complex expression with a controlled phase",
     "Apply phase decomposition or cancellation bounds",
     "Bound boundary terms and nonstationary/stationary regions",
     "Test aligned phases yielding no cancellation", "bound"),
    ("local_to_global", "Local-to-global bridge / 局部整体", "geometry topology algebra", "local 局部 global 整体 glue 拼接",
     "Compatible local solutions and an overlap or descent condition",
     "Glue local objects or identify an obstruction",
     "Verify compatibility on intersections and cocycle conditions",
     "Test incompatible overlaps", "local_to_global"),
    ("minimax", "Minimax interchange / 极小极大", "optimization analysis game_theory", "minimax 极大极小 swap 交换",
     "Clearly stated convexity/concavity and compactness conditions",
     "Compare inf-sup and sup-inf",
     "Prove interchange hypotheses; never assume equality",
     "Test nonconvex zero-sum examples", "change_representation"),
]

def all_operators() -> tuple[Operator, ...]:
    result = []
    seen = set()
    for key, name, domains, triggers, requires, action, obligation, failure, category in _DATA:
        if key in seen:
            raise ValueError("Duplicate operator key: " + key)
        seen.add(key)
        result.append(Operator(key, name, tuple(domains.split()),
                               tuple(triggers.split()), requires, action,
                               obligation, failure, category))
    return tuple(result)


def recommend(goal: str, *, obstacles: str = "", limit: int = 10,
              category: str | None = None) -> list[dict]:
    """Return reviewable *possible* methods, never valid rule applications."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be in [1,100]")
    text = (goal + " " + obstacles).casefold()
    words = set(re.findall(r"[a-z_]+|[\u4e00-\u9fff]+", text))
    results = []
    for op in all_operators():
        if category and op.category != category:
            continue
        hits = []
        for word in op.triggers:
            if (word.casefold() in words or
                    (len(word) >= 2 and word.casefold() in text)):
                hits.append(word)
        # Also allow explicit domain selection as a weaker signal.
        domains = [x for x in op.domains if x in words]
        score = 5 * len(hits) + len(domains)
        if score <= 0:
            continue
        results.append({**asdict(op), "retrieval_score": score,
                        "matched_terms": sorted(set(hits)),
                        "application_status": "proposal_requires_math_verification",
                        "discovery_is_new_theorem": False})
    results.sort(key=lambda r: (-r["retrieval_score"], r["key"]))
    return results[:limit]
