# 数学知识来源、署名和贡献归属

本仓库的目的，是将已有数学知识整理为可查询、可分类、可审查、可用于搜索的
Math-MCTS 系统。**收录、索引、实现搜索算法不代表发现了原始数学定理。**

## 署名边界

| 身份 | 应如何署名 | 不应声称 |
|---|---|---|
| 原始数学定理、推论、定义 | 以原论文、原书籍或历史发现者为准；未知时明确标记待考证 | 仓库维护者发现该定理 |
| mathlib4 中的形式化实现 | mathlib4 项目与相应源模块文件头贡献者；附固定版本源码链接 | 文件头列出的每个人都必然是定理最初发现者 |
| 十万条来源数据 | 引用 mathlib4 对应源码模块、commit 和适用许可证 | 原作者身份已被逐条识别 |
| 本仓库的整理、分类、工程代码 | 仓库实际贡献者 / 维护者 | 继承上游数学成果的原创归属 |
| 未来真正新证明、新算法 | 仅在独立查新、可复核证明和贡献记录后另行认定 | 自动碰撞出候选就认定新成果 |

## 原始数学来源

- 上游数学形式化库：**mathlib4**（Lean 社区贡献者）。
- 官方仓库：https://github.com/leanprover-community/mathlib4
- 当前录入语料的上游来源快照：`54c01c3314d33d15d77893cbe4e0472ff26bb34d`。
- 许可证：**Apache License, Version 2.0**。
- 许可证副本：[`THIRD_PARTY_LICENSES/mathlib4-APACHE-2.0.txt`](THIRD_PARTY_LICENSES/mathlib4-APACHE-2.0.txt)。
- 数学库的单个定理的历史作者、最早论文/教材及准确行号，
  **不能由模块名自动确定**，必须逐条核实。

例如：固定快照中的
[`Mathlib.Algebra.Group.Basic`](https://github.com/leanprover-community/mathlib4/blob/54c01c3314d33d15d77893cbe4e0472ff26bb34d/Mathlib/Algebra/Group/Basic.lean)
源文件头明确写有 *Jeremy Avigad、Leonardo de Moura、Simon Hudon、Mario Carneiro*；
这些是**模块文件头的署名**，不是对模块每一条具体定理最早发现者的断言。

与 mathlib4 不同来源的 16 条导入标准知识卡，不自动套用其 Apache-2.0 版权；
原有人工精选卡也不统一标为 mathlib 原著。来源不明时保留“待补来源”状态。

## 每条知识的可追踪字段

`python tools/build_attribution.py --db math_index.sqlite` 建立独立来源覆盖层，
不修改数学陈述。其输出字段包括：

- `source_project`、`source_project_url`
- `source_commit`、`source_module`、`source_module_url`
- `license`、`original_theorem_author`、`file_header_authors`
- `curation_role`、`mathematics_originality_claim`
- `source_precision`、`raw_source_file`

对于导入的 mathlib 定理，`source_precision` 默认是
`module_level_only_not_exact_declaration_line`；
对应模块 URL 可以确认模块位置，但**不能伪称已经精确找到该声明的源码行号**。
通过单独的原始 Lean 提取核对和源码语句定位后，才能升级这个状态。

### 查询示例

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite
python tools/build_attribution.py --db math_index.sqlite --report source_attribution_report.json

python -m math_mcts knowledge-search "convolution" --db math_index.sqlite --top-k 3
python tools/build_attribution.py --db math_index.sqlite --id YOUR_SOURCE_ID
```

从 `KnowledgeBank.search` / `browse` / `get` 返回的每一条数学知识，
都会附带 `attribution` 来源区块；供 MCTS 使用的导入 `Concept.card()`
也会显示固定来源模块 URL。

## 原始源代码文件头署名

如果需要列出 mathlib 某个模块文件头的作者，必须读取**固定版本**源文件。
不能对模块名做猜测：

```sh
python tools/verify_pinned_mathlib_credit.py \
  --mathlib-root mathlib4 \
  --module Mathlib.Algebra.Group.Basic \
  --output pinned_mathlib_module_credit.json
```

脚本先验证 `git rev-parse HEAD` 与记录的快照提交完全一致，再读取模块
前部的版权声明和 `Authors:` 字段。没有声明时保留空列表，
不得编造或随意转移署名。

原始源码、版权、许可以及修改痕迹应当分别保留；这个来源索引
**不意味着**用户或仓库维护者拥有上游数学成果的著作权。

## 工程失败与数学证明分开记录

Lean 环境成功安装、缓存获取、形式表达式提取、数学语义匹配、
逐步推导证书是独立状态。没有完成真实 Lean 运行的导出，不应标为
内核验证；即使已有来源 SHA，也不意味着作者身份或定理正确性全部完成审查。
