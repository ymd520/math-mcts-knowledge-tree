# 通用 Math-MCTS：类型化等式逻辑层与分层架构

## 本轮架构审查结论

以前的主要可执行推理语言是**有限、显式对象、无函数符号的正 Horn 规则**。知识收集、候选检索、来源审核与 MCTS 调度已经分层，但类似 `f(g(x))` 的内部表达式不能安全地进行数学改写。

因此本轮选择**增加独立等式逻辑层，而不是重构、替换 Horn 引擎**。证明检查器仍然与搜索启发式分离，两个引擎共同使用严格的“候选 ≠ 已审查规则 ≠ 外部数学真理”边界。

```text
Knowledge and evidence layer:
  归档数据 / Mathlib 原文 / 来源与版本哈希
             |
             v
Research candidate layer (untrusted):
  候选定理 / 未验证映射 / 反例建议 / 方法模板
             X  必须经人工或独立形式验证审核才能跨越
             |
             v
Explicit reviewed-rule layer:
  +-- typed positive Horn rule book  (legacy)
  +-- typed equational identity book (new)
             |
             v
Logic-specific construction and search layer:
  +-- semi-naive ground hypergraph + closure/MCTS
  +-- finite contextual equational rewriting + BFS
             |
             v
Independent certificate replay:
  +-- verify_certificate (Horn)
  +-- verify_rewrite_certificate (equational)
             |
             v
Report scope + budgets + original assumptions + rulebook digest
```

搜索可以提出候选，但**不能决定自己使用的规则是真是假**。添加规则必须携带来源，已审核的含义是“调用者明确将该规则视为公理/规则”，不是 Lean 内核已验证、也不是系统自动确定其正确性。

## 新增数学表达能力

`math_mcts.equational` 提供以下基础数学对象：

- `Term.var("?x")`：带显式类型约束的模式变量
- `Term.const("a")`：已声明类型的常量
- `Term.app("f", ...)`：已声明自变量类型与结果类型的函数
- `Equation(lhs, rhs)`：等式两端类型必须相同
- `RewriteRule(id, equation, variables, source, status)`：形式恒等式模板
- `EquationBook`：隔离 `candidate/refuted` 规则、绑定来源/类型与版本指纹
- `prove_equation`：在显式预算内用 BFS 探索**等式的两个方向**以及函数内部任意位置的改写
- `verify_rewrite_certificate`：不使用 BFS 搜索路径缓存，逐步检查替换、位置、类型、前提和来源指纹

例如，如果调用者将 `mul(x,e)=x` 明确提供为已审查公理，则可在 `wrap(mul(a,e))` 内部得到 `wrap(a)`。这验证的是**相对于该公理**的等式推导，并不自动证明该公理在任意数学系统中成立。

有限等式前提可作为**显式局部假设**加入，例如 `a=b`，但它们必须与证书绑定并在独立重放时逐条对照。系统不能凭空产生未声明常量或自由见证变量。

**安全限制**：目前不支持一般全称/存在量词的证明规则、条件等式、绑定变量作用域、偏函数、一般否定、高阶类型、自动解析数学论文或 Lean 环境，也不是完备的等式定理证明器。规则模式变量可作为调用者提供的全称等式模板，但它不是通用量词演算。

## 统一逻辑适配器

`math_mcts.logic_router` 根据显式 `logic` 选择语言：

- `logic="horn"`：保留旧版证明器的约定与证书语义
- `logic="equational"`：新类型化项语言与等式重放
- 缺失或未知逻辑：拒绝猜测，避免跨语言不可靠的自动转换

```sh
python tools/solve_logic.py examples/equational_right_unit.json --output result.json
python tools/solve_logic.py examples/equational_right_unit.json --verify result.json
python tests/test_equational.py
```

输入 `examples/equational_right_unit.json` 同时包含一条未审查候选规则；证明器不会调用该规则。

结果状态 `proved_relative_to_equalities` 只说明存在一个在已声明等式下可逐步重放的推导。没有找到不等于目标不成立；`max_steps`、`max_states` 和 `max_term_nodes` 会导致预算截断，不构成反证。

## 架构上仍需要解决的根本问题

**已做**：将具体逻辑语言、搜索启发式和证书重放拆分；既有 Horn 证明器不承担通用符号表达式的解析职责。新等式逻辑可以服务代数、函数方程、有限代数结构、项改写等数学领域，不偏向特定课题。

**未做**：跨 Horn 与等式的无损联合演算、依赖类型、自由/绑定变量、条件化数学语义、Lean 核级别可验证翻译。不能把“表达能力增加”误称为已解决这些理论障碍。

**后续准入条件**：在增加功能前必须明确逻辑语义、搜索预算、规则的可信来源、证书格式、独立反例与篡改测试，尤其对能改变现有规则库语义的改动必须提供旧版回归测试。

仓库正式目录版本号仍只由统一 manifest 管理；本轮架构优化不增加或修改知识数量/重要性等级，不改正式版本。
