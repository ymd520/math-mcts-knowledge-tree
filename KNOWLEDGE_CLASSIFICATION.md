# 十万数学知识分类导入：知识/重要性/难度三轴架构

本文件描述已经收录与可重建的**数学知识索引层**，不是将未评级的 mathlib
声明自动认证为重要定理。

## 数据层

- **已收录精选库：11,165 条**，带原来的 level、tags 和数学陈述。
- **分类导入来源知识：100,000 条**，来自已经存在的 234,576 条原始声明语料，
  此批由确定性跨来源领域抽样得到。
- 其中 **99,984 条**通过固定 mathlib4 提交的定理声明哈希检查，
  **16 条**原始类型为 `curated_standard_card`，单独标识为来源知识卡待审，
  不假装它们同样是已登记的上游定理。
- **统一分类索引：111,165 条数学知识记录**。它不是 `100,000` 条
  已审核“重要/核心”知识；正式带重要标签的 L1–L4 仍为 6,111 条。

## 三个独立的分类字段

`classified_knowledge` 表记录：

| 分类轴 | 取值/含义 | 自动分类范围 |
|---|---|---|
| 数学知识类别 | `定理声明`、`标准知识卡`、原精选库原始 kind | 可基于原始来源类型执行 |
| 数学领域 | 七大编辑领域与原始 Mathlib 分支、模块路径主题 | 仅按明确的源模块映射；不是自动理解定理 |
| 重要性 | 原精选标签 / `importance_unrated` | 新来源条目均待审，无自动“重要” |
| 难度 | 原精选 Level1–5 / `NULL` | 来源候选原 Level5 是占位，统一留 NULL |
| 来源登记 | 已核对来源定理 / 来源标准卡待审 / 精选库 | 保留本次实际校验等级 |

“数学知识”是一种收录身份，不等于重要性评级或形式化证明。
正因为这一拆分，十万条都能分类检索、给搜索引擎挑选组合对象，
而不会通过强行改名、重复公式或伪造数学分级来增加统计。

## 如何生成和查询

在仓库根目录（Python3.10+，SQLite FTS5）：

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite --manifest official_source_registry.jsonl.gz
python tools/classify_knowledge.py --db math_index.sqlite --report knowledge_classification.json
python -m math_mcts knowledge-search "Fourier" --db math_index.sqlite --top-k 8
python -m math_mcts knowledge-browse --db math_index.sqlite --domain 代数 --kind 定理声明 --limit 10
python -m math_mcts knowledge-show SOME_SOURCE_ID --db math_index.sqlite
```

API：

```python
from math_mcts import KnowledgeBank
bank = KnowledgeBank("math_index.sqlite")
results = bank.search("convolution", domain="分析", top_k=10)
page = bank.browse(domain="代数", after_id="", limit=100)
concept = bank.get(results[0]["id"]) if results else None
```

`KnowledgeBank` 是有界加载的可索引目录，不会每次把十万条数学陈述
反序列化成 `Concept`。默认读取每次只返回一小批结果。
`source_subfield`/`source_topic` 来源于模块命名空间，
是供搜索和导航使用的**源代码分类标签**，
并非经过数学专家审定的完整知识本体。

## 持久性和审计

仓库中保留压缩原始声明分片、SHA256 manifest、登记/分类代码和测试；
CI 会实际构建完整 100,000 条分类 SQLite 视图并上传统计结果
`knowledge_classification.json`。SQLite 数据库是可从 Git 仓库原始语料
**重复生成的工作索引**，不是直接随 Git 提交的超大二进制文件。

改动来源分片时，原有压缩源 SHA256 会拦截失配；重建数据库时
来源登记与分类总数必须严格一致，且所有新来源条目的重要性和难度
必须仍处于待评级状态，否则拒绝成功报告。

## 下一轮真正的“重要”审核

根据课程核心性、被引用频率、跨领域复用性、数学内容正确性和
独立审核的教育难度分批评估。经验证后才可提升重要等级；
`importance_unrated` 并不表示“不重要”，而是**尚未知晓**。

自动提出新猜想、自动反例与完整形式化证明链目前不纳入验收范围。
