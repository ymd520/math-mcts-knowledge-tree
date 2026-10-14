# 全量 Lean 提取、数学结构审核与来源署名：状态账

## 本轮三阶段顺序（跳过原计划阶段 3）

**阶段 1：全部 99,984 条**原始注册的 mathlib 定理是完整工作范围，
不再把 1,000 条当作最终目标。旧批次仅实提取 6 条；
新方案按固定 mathlib4 SHA 将所有 source IDs 编入一次完整计划，
每批最多 60 条、按模块组织、支持 8 个工作节点执行和来源完整性审计。

“编入全量计划”不等于“已完成全部形式化提取”。本项目明确区分：
- 已登记：原始来源文本与 SHA 已核对；
- 已计划：存在确定性批次，异常/Unicode 名称不允许静默忽略；
- 已执行：确切固定 mathlib commit + Lean 版本的运行有收据；
- 已提取：Lean 运行输出与原 source_id、模块和 hash 对齐；
- 未完成：运行超时/编译失败/名称缺失/未执行，逐项计数；
- 已验证数学推导：**本轮没有因依赖提取而自动升级任何定理**。

执行工作流 [`.github/workflows/mathlib-full.yml`](.github/workflows/mathlib-full.yml)
在合并到主分支后启动 8 个工作节点，每个节点的时间预算由配置约束。
运行不完时保留成功批次的收据和 JSONL，并将总覆盖率标为 `complete=false`，
最终完整覆盖关卡必须报失败。需要后续续跑时，通过
`workflow_dispatch` 提供此前的 `resume_run_id`，经校验后复用其有效收据。
**不保证一次受限 CI 能完成全部 99,984 条**，不得将失败判为数学错误。

命令：

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite
python tools/plan_full_lean.py --db math_index.sqlite --output mathlib_full_plan.json --report mathlib_full_plan_report.json
# 需提前检出原始固定 mathlib SHA/Lean 环境
python tools/run_full_lean_worker.py --plan mathlib_full_plan.json --mathlib-root mathlib4 --out full_results --worker 0 --workers 8 --max-seconds 3600
python tools/audit_full_lean.py --plan mathlib_full_plan.json --receipts full_results --report full_lean_coverage.json
# 有且仅有100%成功才让下条命令通过
python tools/audit_full_lean.py --plan mathlib_full_plan.json --receipts full_results --require-complete
```

## 阶段 2：真正来自 Lean Expr 的结构及“不能证明”标记

每条在 Lean 环境找到的声明可以报告：
- `type_expression`：Lean elaborated type 的打印表达式；
- `leading_pi_binders`：`Expr.forallE` 开头绑定数量，可能是类型、
  实例、隐式参数、数学量词，也可能是逻辑前提，**不能等同于证明条件数**；
- `elaborated_type_head`：表达式首层构造类型；
- `type_references`、`proof_references`：常量引用，而非可组合推理边。

`math_mcts.full_lean_import.ingest_full_receipts` 按来源 hash 增量导入，
保留已有成功提取结果、拒绝冲突，永不因一次失败清空全库。
`indexed_type_conditions` 显式返回 `logical_assumptions_verified=false`
和 `usable_as_horn_rule=false`；未经另行严格审查与证书重放，不得
将来源引用变为可信 Horn 规则。这次完成的是**结构化语义基础层**，
不是十万条类型理论到 Horn 逻辑的完整翻译。

## 阶段 4：全部来源审计队列与成果归属

`tools/export_full_review_backlog.py` 为全部 source_registry 里的定理生成
独立 `JSONL.gz`，保留：

- 精确来源项目 mathlib4、固定 commit、模块 URL、源码内容 hash；
- 许可声明 Apache-2.0 和模块版权/作者归属边界；
- 具体定理的历史发现者若没有外部证据则标 `not_verified`；
- 重要性、难度、审核人、审核日期及尚未审查状态；
- 已完成的 Lean type 指纹（若有），无则为 null；
- 未经校验不标为用户原创或经证明的全新定理。

```sh
python tools/export_full_review_backlog.py --db math_index.sqlite --output full_source_review_backlog.jsonl.gz
```

已核查来源的可自动整理部分全部入账，真正的数学内容重要性和
历史最早发现者仍须借助可信文献与人工复核，
**绝不因为目标要求十万条就虚构十万个学术审核结论**。
若需要升级来源知识的“重要”和 Level，必须使用现有
`math_mcts.editorial` 显式审阅门槛，并核对准确来源指纹和数学内容。

## 不执行阶段 3

按用户本轮要求，暂不开展 20 层 × 20 条知识真实证明
与 BFS/束搜索/MCTS 对比实验。原有基本回归测试继续保留，但不是
本轮评估重点。

## 运行规模与失败核算

8 个 GitHub Actions 工作节点不是无限资源。一次执行可能超时、
产物保留有期限，并且 GitHub Actions 有计算额度及仓库权限限制。
必须报告 `registered_total`、`scheduled_total`、
`unsupported_declarations`、`executed_and_source_exported`、
`lean_missing_declarations`、`failed_or_incomplete_declarations`、
`not_run_declarations`；只有全部成功方为 `complete=true`。
