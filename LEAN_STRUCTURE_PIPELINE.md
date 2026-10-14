# Lean 类型与依赖提取：严格可验证范围

## 数据源锁定

已有 mathlib 导入来源固定为：
- **mathlib4 commit**: `54c01c3314d33d15d77893cbe4e0472ff26bb34d`
- 对应原仓库的 **Lean toolchain**: `leanprover/lean4:v4.35.0-rc4`

这与单独的 Lean Core 编译烟测工具链 **v4.34.0** 不同。
Core smoke 只验证提取程序确实读过 Lean 环境中经过 elaboration
的 `ConstantInfo.type` 与 `ConstantInfo.value`。
它绝不意味着已对 mathlib4 的十万条定理执行同样的提取。

Lean 库的 `Expr.getUsedConstants` 会给出表达式中的语法常量引用，
而非已经证明可组合的逻辑规则；证明项引用也不表示该前提不可替代。

## 处理链

```
100k 原来源声明（固定提交+SHA）
      ↓
source_registry（登记精确来源）
      ↓
Lean 环境表达式提取（独立运行、与原版本兼容）
      ↓
逐条对齐 ID / 完整命名空间 / 模块 / 源指纹
      ↓
lean_declaration_export  （类型表达式 / 声明级别）
lean_dependency_edges   （类型引用 / 证明项引用）
      ↓
反向依赖检索 → 已审数学关系筛选 → 目标搜索
```

上述最后一步是未来真正的数学推导操作。
**语法常量依赖绝不能直接当作 Horn 推理规则**，
否则会违反类型、局部假设、量词和剩余证明条件约束。

## 当前可用命令

```sh
# 和此前一样建立来源、分类索引
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite

# 固定来源的模块级训练/验证/测试切分
python tools/build_lean_holdout.py --db math_index.sqlite --report lean_module_holdout.json

# 生成小规模 mathlib 提取请求，需在 *固定提交对应 toolchain* 下运行
python tools/generate_mathlib_extraction.py --db math_index.sqlite \
   --limit 20 --output lean/ExtractSelected.lean

# 必须从已 checkout 到确切 SHA 的 mathlib 项目中运行，
# 然后用其 Lake 环境对 ExtractSelected.lean 执行 Lean 处理。
# 将程序输出中成功提取的 JSON 对象收集成 JSONL
# （遗漏/失败的请求须独立记录，不得估计覆盖率）。

python tools/import_lean_extraction.py --db math_index.sqlite \
  --jsonl real_lean_export.jsonl --report lean_reference_report.json

python tools/import_lean_extraction.py --db math_index.sqlite \
  --inspect REGISTERED_SOURCE_ID --max-hops 4
```

导入验证拒绝缺失的来源 ID、模块不一致、mathlib commit 不一致、
定理名不一致、原陈述被篡改、重复 ID/完整定理名、过大的记录等。
导入记录明确标记 `external_export_unattested`。
**任意人提交的 JSON 即使写了 `verified_by_kernel=true` 也无法变成
已证明的数学事实。** 只有可信 CI 的真实 Lean 执行证据能建立
“此表达式确实来自该运行”的工程证据；仍需审计声明语义一致性。

## 性能与真实任务测试

- `math_mcts.adaptive_search.solve_adaptive` 默认把小型、完整的推导图交给 BFS；
  部分大型、窄分支任务交给 beam，宽分支任务交给 MCTS；
  有损截断总是保留 `graph_complete=false`。
- 成功推导仍使用现有 `RuleBook` 和证书重放。自动选择并不保证最优或加速。
- `math_mcts.lean_holdout` 按源模块整体拆分数据，
  避免同模块的不同定理同时分配到训练集/测试集。
  跨模块依赖与知识重述仍可能泄漏，需更强的语义去重。
- 原先三个初等数学测试和 20×20 人工构造规则图仍保留，
  **未证明在真实研究级问题上能做到20层、每层20条有效知识**。

## 交付性质

本轮目标是把可信**提取基础设施**和**真实 CI Lean 运行**接入系统，
并提供高效、有界的依赖查询与搜索路由。
十万条 mathlib 定理的真实全量形式表达式提取、依赖覆盖统计、证明目标
完整形式化，以及与其他搜索器在大规模真实任务上的公平性能优势，
仍需要进一步运行与独立验收。
