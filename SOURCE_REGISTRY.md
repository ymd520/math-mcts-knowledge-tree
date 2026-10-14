# 正式来源数学声明目录：证据边界及批量收录结果

## “正式登记”不是“重要定理审核”

当前 Math-MCTS 数据具有不同的层次：

1. **来源声明（source statement）**：有原始声明、模块、固定来源提交和
   可复核的完整陈述 SHA256；经过一致性验证后可在
   `source_registry` 表中**正式登记并检索**。
2. **重要知识（editorially important knowledge）**：在来源声明之外，
   需要能明确说明它为何是重要的数学知识，核对适用条件和语义同一性，
   确认真正的 Level 1–4 教育难度并独立标记为“重要”或“核心”。
3. **本次运行核验**：不是以上任何一项自动成立。代码没有重新运行 Lean
   或独立证明公式正确。

不能把固定版本 mathlib 中的全部声明等同于重要定理，尤其不能把
它们原始的 `level=5`（未评级占位）均匀涂改为 Level 1–4。

## 本次新增的正式来源目录

`math_mcts.source_registry` 从已经完成导入分片 SHA256 检验的 FTS5 索引中
逐条做以下机械核查：

- 原始元数据的类型确实是 `upstream_theorem`；
- 英文定理名、`Mathlib.` 模块名以及形式陈述均非空；
- 陈述以对应的 `theorem 名称` 开始且内容不为空；
- 从原文重新计算的 SHA256 与原始元数据的
  `陈述SHA256` **精确一致**；
- 登记 ID 和陈述内容指纹不重复。

只有满足全部条件的条目才获得**正式来源登记**；
未通过者仍在待审列表，并输出逐项失败原因与数量。
登记内容保存不可变来源提交：
`54c01c3314d33d15d77893cbe4e0472ff26bb34d`。

运行方式：

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite \
  --manifest official_source_registry.jsonl.gz --report source_registration_report.json
python -m math_mcts search-index "group" --db math_index.sqlite --registered-only
python -m math_mcts show-registered YOUR_SOURCE_CONCEPT_ID --db math_index.sqlite
```

CI 会实际运行上述登记过程，发布注册清单 `official_source_registry.jsonl.gz`
和拒绝计数 `source_registration_report.json`。
是否有全部 100,000 条满足登记门槛，以 CI 报告为准；**本文件不预设结果**。

### 重要性审查仍缺什么

满足来源完整性只是第一道关。要计入“正式 Level 1–4 重要知识”目标，
还必须通过数学语义审核、重要性理由、正确教育分级、去重和依赖关系核对。
目前真正已标记重要/核心且等级处于 L1–L4 的正式库仍为 **6,111 条**，
十万目标缺口为 **93,889 条**。不要因成功注册来源声明而改变这一统计。

不同的数据标签不可互相冒充：

- `registered_statement=true`：来源指纹核对通过；
- `reviewed_importance=false`：未完成数学重要性审核；
- `reviewed_level=null`：未完成难度评级；
- `proof_verified_this_run=false`：本次没有重新运行证明内核。

相关任务：[SCALING_100K.md](SCALING_100K.md)、[CURATION.md](CURATION.md)、
[GitHub Issue #4](https://github.com/ymd520/math-mcts-knowledge-tree/issues/4)。
