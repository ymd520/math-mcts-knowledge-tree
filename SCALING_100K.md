# 十万条 Level 1–4 重要知识目标：现状、索引与审核门槛

## 数量定义

**目标：正式审定的 Level 1–4 重要或核心知识，各 25,000 条，合计 100,000。**
此数是验收目标，不是当前已完成的数据量。现有数量：
L1=805, L2=1356, L3=2216, L4=1734，总计 6111。
缺口 L1=24195, L2=23644, L3=22784, L4=23266，共计 93889。

另外有 234576 条来源索引语料，其中大多为 mathlib 形式化声明。
导入文件中的原始 level=5 **只是未评级占位**，不可视为学术难度5，
更不可直接把它们重新标成 Level 1–4 重要知识。

## 已实现的十万规模分离式架构

`math_mcts.fast_index` 建立 SQLite FTS5 索引。它：

- 从正式知识库读取原卡（保留难度与重要性状态），从导入分片校验 SHA256 后提取**未审候选**；
- 对导入候选按数学领域轮转选取，避免只抽取前几个压缩分片；
- 中文单字、双字、三字与英文术语构建倒排索引，查询仅返回候选小集合，不加载整库 Concept；
- 用 `tier=curated` 与 `tier=unreviewed_import` 分离检索，并将**未审候选 level=NULL**，不污染正式等级；
- 将十万候选以 JSONL 压缩审核队列形式导出，带源ID、原声明、模块与源指纹；实际级别/重要性判定留空；
- 不用生成同义句/重命名/参数实例来增加虚假知识数量。

本地复现：
```bash
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000 --summary index_status.json
python tools/build_search_index.py --db math_index.sqlite --query "finite group"
python tools/export_review_queue.py --db math_index.sqlite --output source_review_queue.jsonl.gz --summary scale_status.json
python tools/benchmark_fast_index.py --db math_index.sqlite --output fts_benchmark.json
```

在 CI 的 Python 3.12 环境完整运行并发布 `source-candidates-100k` artifact；
仅当该轮 Actions 成功时，方可宣称**已实际构建十万条待审核候选索引**。
指数大小、查询延迟、可用性须以该轮 CI 报告为准。
数据库是再生缓存文件，不提交到 Git：避免更新一次数据就导致巨大二进制差异。

## 正式升级到“重要”的严格要求

每条候选需要：（1）唯一数学陈述、非改名复述；（2）具体且可复查的来源（
源码提交/模块/定理名，教材要精确到定理或页码）；
（3）关键假设、适用对象、结论无缺失；（4）重要性理由，必须满足
`CURATION.md` 的课程/经典引用/工程使用标准；
（5）依实际理解门槛定 Level1–4，禁止按配额调级；
（6）与既有同名/同结论知识核对；
（7）经过人工编辑与审稿，保留来源的状态、审核签名、日期和来源指纹。

只有通过上述审核并写入正式补充包的条目才计入 Level 1–4 的 100,000 目标。
同名不一定重复，不同名也不一定是不同定理；不能仅凭字面去重保证语义唯一。
现有 7414 条来源定位缺口亦须逐项核对，不可凭链接补齐冒充核验。

## 三项工程改进

1. **正确性**：证书规则指纹包含原知识卡ID、内容 SHA256 及映射审核声明；
   目标已掌握的学习路径返回正确目标，不拼接无关已掌握知识。
2. **数学语义**：`semantic_links.find_composable_rules` 在已经审查、类型化的 Horn 规则间
   以结论—前提统一、重复变量及常量冲突判断合法接边，输出**待补条件的组合候选**；
   不能把该连接当作新定理或证书。
3. **性能与质量**：十万候选的离线哈希校验、按领域分配索引、FTS 短名单快速检索、
   真实性审查队列、GitHub 100k 构建/延迟基准、全库结构审计；
   MCTS 碰撞候选排序只做一次。

## 延后事项

自主提出数学猜想、自动反例搜索、Lean自动证明闭环已由用户明确暂缓。
引擎的实际数学价值仍需在独立的数学问题集上与 BFS/逆向推理/启发式搜索比较。
