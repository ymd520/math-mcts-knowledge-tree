# 十万来源定理：全量 Lean 提取、结构化条件和原始署名

**本轮范围：阶段一、阶段二、阶段四。阶段三（真实复杂数学证明性能对照）按要求暂停。**

## 总账：执行状态与数学结论分离

- 输入为 `source_registry` 中**实际登记的 99,984 条上游定理**。
  另 16 条是非定理标准知识卡，不能伪造为已在 Lean 环境中的定理。
- `plan_full_mathlib.py` 扫描**全部 99,984 个来源 ID**，
  按来源模块形成 64 个稳定分片，每模块进一步按最多 80 条分批。
  有命名空间或 Lean 标识符不支持的记录列入 `blocked`，
  不会默默丢弃或视为成功。
- **计划覆盖=99,984** 不等于 **真实 Lean 提取成功=99,984**。
  实际提取数量只以 `aggregate_mathlib_results.py` 的
  `extracted` 字段为准。网络、缓存、内存、Lean 编译问题和
  无法在真实环境定位的定理均计作未完成。
- 所有来源保持 mathlib4 固定 commit
  `54c01c3314d33d15d77893cbe4e0472ff26bb34d`，
  且使用该提交的 `leanprover/lean4:v4.35.0-rc4`。
  不允许为了改善成功率而悄悄改 Lean/mathlib 版本。

## 阶段一：全量分片与独立验收

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite
python tools/plan_full_mathlib.py --db math_index.sqlite \
  --output full_mathlib_plan --shards 64 --batch-size 80
python tools/plan_full_mathlib.py --output full_mathlib_plan --verify-only
```

正式执行采用 `.github/workflows/full-mathlib.yml`。其 `workflow_dispatch`
支持 `shard=all`（64 分片）或指定 `0..63`（定点重试），最大
4 个分片同时运行，最长 300 分钟/分片。大规模编译可能耗费很多
**GitHub Actions 分钟、网络传输和缓存配额**，因此默认需要用户在
GitHub Actions 手动触发；PR 的日常 CI 只检查全量计划和
实际 Lean 小样本，不暗中启动数十个昂贵的构建器。

每个分片会写：
- `status.jsonl`：每个来源 ID 的终态：`extracted`、
  `not_found_in_lean_environment`、`lean_timeout`、
  `cache_or_build_failed`、`source_module_missing_at_pinned_commit`、
  `lean_error_or_no_output` 等。
- `extracted.jsonl`：仅包含**实际 Lean 环境返回且指纹匹配**的记录。
- `report.json`：包含已处理、成功、失败、未处理数量。
- `aggregate_mathlib_results.py` 统一核验**全部登记来源**，
  拒绝双重 ID、SHA 变化、虚报成功、遗漏源数据。
- `all_lean_extracted.jsonl`：严格对齐后的真实 Lean 结构导出。

注意：独立提交的导出 JSON 依然标为外部来源待核；
可信 GitHub CI 提取日志可以提供相应运行证据，但 JSON 声称
`verified_by_kernel` 不能独立证明它曾经过 Lean。

已验证样本：此前 CI 成功提取 6 条真正的 mathlib 声明。
这份新工作流面向全部 99,984 条；**全量真实提取是否完成，必须
由实际完整执行结束后的统计证明，不能提前宣称。**

## 阶段二：真正的 Lean 类型结构

从 `Lean.Expr` 而非自然语言标签提取：
- 所有开头 `forallE` 绑定名、绑定领域的 Lean Expr AST、
  `BinderInfo` 和绑定类型所引用的常量；
- 剥离顶层绑定后的结论 Lean Expr AST；
- 定理原始类型表达式与证明项使用的常量。

`math_mcts.lean_type_semantics` 将其写为：
`lean_type_structure`、`lean_type_binders`。具有相同
原始 AST 的定理结论与某个规则绑定领域可以出现在
`candidate_type_connections` 中，但这**只是待检查的前提匹配**，
存在局部变量、隐式类型类、宇宙约束和剩余前提时尤其不能直接视为证明。

新增实际 Lean Core 烟测同时检查：
1. `forallE` 对应的真实绑定类型结构和结论 AST 能否正确读出；
2. `Lean.Meta.isDefEq` 对两个闭合命题判断真实类型一致，
   对反例拒绝匹配；
3. 这些检查不等于消除了消费者定理的其他前提，
   不自动形成可信数学证明或“原创新定理”。

```sh
python tools/index_lean_type_semantics.py --db math_index.sqlite \
  --exports all_lean_extracted.jsonl \
  --report lean_type_semantics_report.json
```

## 阶段四：引用与实际贡献者归属

`tools/index_mathlib_source_credit.py` 要求源码目录的
`git rev-parse HEAD` 与固定上游 commit 完全相同，
然后逐个读取登记源模块文件头：

- 每个实际源文件的 SHA256、Authors、Copyright、
  固定模块相对路径与固定 commit；
- 所有 mathlib 登记定理 ID 连接对应模块信用记录；
- 原文件未标作者或源文件不存在时明确标记待核，
  **绝不补写猜测人名**；
- **源文件贡献者不等于每条数学定理的历史发现者**；
  原论文/书籍作者需另外逐一核实和引用；
- 原库 Apache 2.0 保留第三方许可证副本，原精选库或其他来源
  不自动继承 mathlib 的授权身份。

```sh
python tools/index_mathlib_source_credit.py --db math_index.sqlite \
  --mathlib-root mathlib4 --report all_mathlib_source_credits.json
```

这份来源数据是知识整理者、原始数学成果作者和 mathlib 形式化
贡献者之间的**引用账本**，不会变更原始作者身份。

## 尚待真实验收的条件

只有当分片汇总证实**99,984/99,984 都来自匹配版本真实 Lean 环境**
且没有未处理/失败项时，才可宣布阶段一“完整提取”。

阶段二还需要对候选类型连接逐一执行更全面的 Lean 上下文证明义务
核验；当前的结构提取与闭合前提等价性检查不等同于普遍定理组合
的形式化证明。

阶段四的模块文件头自动整理可以批量完成，但
**原数学定理的历史发现者与精确论文引用无法靠头部信息自动确定**；
未知项仍然需要可靠文献核查，不能声称全部补完。

所有实际工程产出应以 CI 日志、精确源 commit、SHA256、
`report.json`、来源署名索引和失败清单为凭证。
