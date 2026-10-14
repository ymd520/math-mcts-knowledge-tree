# 十万条数学知识：证据优先的质量审查

## 任务分层（严格区分事实、候选判断与未知）

`KNOWLEDGE_CLASSIFICATION.md` 已实现 **111,165 条**统一索引，其中
**100,000 条**来自 mathlib 导入。来源注册中的 **99,984 条**经过原始定理
文本 SHA256 一致性核对，**16 条**属于另列的来源标准知识卡。

这只证明原始记录可以追踪，并不说明每条定理重要、数学语义正确或属于
Level 1–4。此前已有正式的重要/核心等级标记合计为 6,111 条；未审核
重要性不等于“不重要”。

## 第一轮已实现：十万条全量可解释的质量信号

运行 `math_mcts.review_quality.review_signals`，在 SQLite 中创建
`knowledge_review_signals` 表；每条来源记录恰好一行，可复现，支持
不加载全部源记录的索引查询。信号包括：

| 可复核信号 | 表示的事实 | 不意味着 |
|---|---|---|
| `lexical_name_matches_curated` | 与现有精选库某个足够长的名称字符串匹配 | 同一定理、重要性已证 |
| `specialized_module_topic` | 所属模块为明示的研究数学分支 | 必然 Level 4/5 |
| `same_name_count>1` | 不同源条目规范化名称重复 | 语义重复 |
| `same_statement_count>1` | 去除源定理名称并折叠空格后的陈述相同 | 已完成数学去重 |
| `placeholder_keyword_in_source_text` | 原形式文本含 `sorry`/`admit` 词 | 形式化证明失败（没有运行证明内核） |
| `very_short_formal_statement` | 陈述文本很短 | 数学内容错误 |
| `module_locator_needs_review` | 模块名不符合预期命名空间 | 数据来源一定无效 |

`review_priority`：按既有精选库英文标题锚点和重复家族的**候选审核收益**
排序，不是重要性概率或数学评分。

`anomaly_score`：对占位关键词、来源异常、疑似重复做**质检优先级**，
不是定理错误率。分数没有外部校准，不能据此推断通过/失败概率。

`review_bucket`：`curated_title_review`、
`specialized_subject_review`、`general_source_review`，
都是审稿任务路径，不是 Level 1–4 分类。

## 运行与查验

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite
python tools/review_quality.py --db math_index.sqlite --report quality_triage_report.json --output quality_review_top1000.jsonl.gz
python -m math_mcts knowledge-review --db math_index.sqlite --mode priority --limit 30
python -m math_mcts knowledge-review --db math_index.sqlite --mode anomaly --limit 30
python -m math_mcts knowledge-review --db math_index.sqlite --mode duplicate --limit 30
```

CI 的 Python 3.12 运行必须扫描所有十万条来源记录，核对行数和无自动
重要性/难度升级；生成三个前一千条的压缩评审队列和总体统计报告。
这是可重复构建的质量检查，不会修改原始知识卡的事实/数学状态。

## 下一步的真实数学审核流程

1. 从审查队列中挑选有明确原始来源与重要性线索的条目。
2. 对照源声明原文检查变量、量词、假设、结论；找到文献中的精确定位。
3. 对具有相似名称或规范化陈述的条目人工判断是否真为同一命题、
   是否仅换命题参数，以及是否值得合并。
4. 依照 `CURATION.md` 的课程、经典结果、可复用性标准，记录
   具体的 **importance_reason**。名称或模块本身不能作唯一依据。
5. 独立根据实际学习难度给出 Level 1–4（或 Level 5）。
   不按每级两万五千条配额调级；如配额与知识实际难度冲突，以事实为准。
6. 明确审核责任、日期和原陈述指纹后再写入人工编辑层，保留
   原始内容可追溯，不覆盖上游导入原记录。

**暂缓范围**：用户此前明确暂停自动猜想生成、独立反例引擎、
Lean 自动证明闭环。上述工作不依赖这些模块。
