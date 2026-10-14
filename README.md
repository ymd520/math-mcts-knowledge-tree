> **数学成果来源与署名说明：** 本仓库的 Math-MCTS 软件、知识整理及索引工作，与被收录数学定理的原创发现是不同贡献。来自 mathlib4 的导入声明归属 mathlib 社区及其上游原始数学来源，并保留固定源码模块、提交指纹及 Apache-2.0 许可；具体定理的最早发现者未逐条核实时应标为未知。详情：[来源、署名与引用规则](ATTRIBUTION_AND_SOURCES.md)。

# 数学知识 MCTS 搜索树

当前正式知识目录版本：**v1.15.0**；新增十万规模未审来源候选索引能力。纯 Python 标准库，Python 3.10+。

将数学知识组织为领域→分支→主题→概念，支持知识检索、学习路径、知识配对，
以及相对于明确审核规则的多前提、多层推导。MCTS用于搜索调度，
搜索次数和深度不代表数学原创性或证明真实性。概念检索对全量知识精确评分，“核心”“重要”标签加权，并可用 `--important` 过滤；此检索不伪称为 MCTS 迭代；MCTS 仍用于知识配对和规则调度；学习路径已改为完整先修拓扑规划，避免无关随机绕路。

## 当前知识数量

基础库现为10974条；补充分片新增495条；Level 1–3专题深化包176条；默认统一加载11645条。\nLevel 1–4 已标记重要/核心知识5820条；未审核来源候选不计入此数。
59条旧知识补充条件、结论和参考来源；603条按依赖引用标为结构上重要，
这两类不是新增知识。原始导入语料234576条另行统计，不等于同样数量的
重要定理或已经审核的概念。

| 难度 | 重要/核心知识：之前 | 当前 |
|---|---:|---:|
| level1 初中基础 | 87 | 857 |
| level2 高中与微积分入门 | 544 | 1316 |
| level3 大学基础 | 1671 | 2135 |
| level4 大学进阶 | 1442 | 1512 |

重要性、难度、内容核验程度分别记录。部分旧等级尚待重评；新卡片的编辑检查
不是Lean验证，来源网址为主题参考，不是逐条定理证明定位。
详见[目录架构](CATALOG_ARCHITECTURE.md)和[收录规范](CURATION.md)。

## 十万条来源候选与快速检索（不同于正式重要知识）

已有 mathlib 来源索引 234,576 条未经逐条核验的数学声明；其中原始 level5
为“未评级”占位，不能按字面计算为难度5、也不能凭配额改为 Level1–4 重要。
构建器现已通过 GitHub CI 实测：**正式卡 11,645 + 来源候选 100,000 = 索引记录 动态分类总量**。
十万条候选在索引中标记为 `unreviewed_import`、`level=NULL`；
Level 1–4 重要知识为 5820 条；来源候选仍不计入重要知识。

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000 --summary index_status.json
python -m math_mcts search-index "convolution" --db math_index.sqlite --top-k 10
python -m math_mcts search-index "矩阵" --db math_index.sqlite --tier curated
python tools/export_review_queue.py --db math_index.sqlite --summary scale_status.json
python -m math_mcts scale-status --db math_index.sqlite
python tools/benchmark_fast_index.py --db math_index.sqlite
```

搜索采用 SQLite FTS5 中文一、二、三字索引及英语词汇倒排；小候选集重新排序，
不需要每次反序列化全部知识。数据库是可再生缓存，不与正式补充包混放。
详见 [SCALING_100K.md](SCALING_100K.md)，含真实数量、分级审核门槛及限制。

人工审核规则可以用 `python -m math_mcts semantic-links <problem.json>`
寻找类型、变量及常量不冲突的前提—结论接边；
结果只是**待满足前提的组合候选**，不是数学证明。

## 正式来源数学声明登记

可对已完成 SHA256 来源校验的 mathlib 候选运行单条声明重算，
产生可重复构建的正式来源登记清单。它不会自动把所有导入声明标记为
Level 1–4 重要知识（这一评级仍需内容审查）。

```sh
python tools/register_source_statements.py --db math_index.sqlite --manifest official_source_registry.jsonl.gz
python -m math_mcts search-index "matrix" --db math_index.sqlite --registered-only
```

详见 [SOURCE_REGISTRY.md](SOURCE_REGISTRY.md)，CI 实际登记数量以
`source_registration_report.json` 为准。

## 数学知识层：已分类接入十万条来源声明

`KnowledgeBank` 将正式精选知识与十万来源知识放进同一分类索引，
但重要性与难度评级彼此独立。十万条来源中，
99,984 条经定理来源指纹登记；另外 16 条为单独标记的标准知识卡。
新导入知识**全部可检索**，但重要性和教育等级保持“待评估”。

```sh
python tools/build_search_index.py --db math_index.sqlite --candidate-limit 100000
python tools/register_source_statements.py --db math_index.sqlite
python tools/classify_knowledge.py --db math_index.sqlite --report knowledge_classification.json
python -m math_mcts knowledge-search "Fourier" --db math_index.sqlite --top-k 10
python -m math_mcts knowledge-browse --db math_index.sqlite --domain 代数 --kind 定理声明 --limit 20
```

分类依据源代码数学领域、分支和模块路径，不冒充真正完成所有定理的
语义分类；重要性与 Level 分级也不自动提高。
详见 [KNOWLEDGE_CLASSIFICATION.md](KNOWLEDGE_CLASSIFICATION.md)。

## 数学知识质量审查（十万条实际数据）

对 100,000 条已导入来源知识进行逐条可复现的结构质检，
生成重要性审核线索、同名/规范化陈述疑似重复组、来源异常排查清单。
**审核线索并不改变知识的重要性、真实难度或证明核验状态。**

```sh
python tools/review_quality.py --db math_index.sqlite --report quality_triage_report.json
python -m math_mcts knowledge-review --db math_index.sqlite --mode priority --limit 20
python -m math_mcts knowledge-review --db math_index.sqlite --mode anomaly --limit 20
python -m math_mcts knowledge-review --db math_index.sqlite --mode duplicate --limit 20
```

需先运行上节的索引、来源登记和分类生成命令。详见
[REVIEW_PIPELINE.md](REVIEW_PIPELINE.md)。CI 会实际扫描全量十万条来源。

## 快速调用

```sh
git clone https://github.com/ymd520/math-mcts-knowledge-tree.git
cd math-mcts-knowledge-tree
python -m math_mcts info
python -m math_mcts search "分数除法" --levels 1,2 --important
python -m math_mcts search "支配收敛" --levels 3,4 --important --domain 分析
python -m math_mcts show "概率一不等于处处成立"
python -m math_mcts path "傅里叶变换"
python -m math_mcts collide --levels 1,2,3,4 --important --top_k 10
```

```python
from math_mcts import KnowledgeTree, search_concepts, collide_concepts

tree = KnowledgeTree.load()  # 基础库+哈希校验补充包+绑定原内容的覆盖层
scope = tree.select(levels=[1,2,3,4], important_only=True)
print(scope.inventory())
results = search_concepts(scope, "概率 零事件", top_k=10)
pairs = collide_concepts(scope, top_k=10)
print(tree.find_all("Addition commutativity"))
```

检索视图保留原先修ID，可能存在视图外依赖；学习路径应使用完整树。
`find_all`保留同名多义条目，不盲目删除或合并。

## 导入知识模块

```python
tree = KnowledgeTree.load_imported(
    module_prefix=["Mathlib.Algebra.Ring", "Mathlib.Analysis.SpecialFunctions.Log"],
    include_curated=True)
```

模块索引只读取相关压缩分片，校验来源哈希。导入声明保留原始来源、假设和
审核状态；符号引用不当作已确认的先修依赖。参见
[导入说明](imports/mcts_text_20261013/README.md)。

## 多前提和多层推导

```sh
python -m math_mcts derive examples/extreme_value.json --iterations 80 -o report.json
python -m math_mcts verify-derivation examples/extreme_value.json report.json

python examples/layered_collision.py --width 20 --layers 20 -o layered_problem.json
python -m math_mcts derive-layers layered_problem.json --iterations 5 -o layered_report.json
python -m math_mcts verify-layers layered_problem.json layered_report.json
```

`collide`是知识配对检索；`derive`和`derive-layers`是相对于明确审核Horn规则
的可重放推导。分层模式要求每层至少20个不同目标相关前提、至少20层、
目标实际依赖深度至少20。条件不足时明确失败，不用重复知识或无关分支凑数。
20×20示例是合成架构测试，不是400条新数学定理。

知识文本可进入`DiscoveryQueue`候选区，精确翻译并审核后才可成为RuleBook规则。
尚未接入全库自动翻译、Lean内核、通用猜想发现或自动反例后端。
详见[推导架构](REASONING.md)与[分层碰撞](LAYERED_COLLISION.md)。

## 项目结构

| 路径 | 职责 |
|---|---|
| math_mcts/knowledge.py | Concept、统一加载、别名、层级与先修依赖 |
| math_mcts/catalog.py | 补充分片、哈希绑定覆盖层和数量统计 |
| math_mcts/search.py | 拓扑学习路径、精确概念检索、启发式知识配对 |
| math_mcts/mcts.py | 通用MCTS调度接口 |
| math_mcts/reasoning.py | 类型化多前提规则与证书重放 |
| math_mcts/layered.py | 同步批次碰撞、真实宽度/深度检查 |
| math_mcts/data/curated/ | level1–4补充包、清单与审计记录 |
| tools/build_curated_catalog.py | 从独立编写的文本可复现构建补充包 |
| source_index/ | 固定版本mathlib4源码索引，与编辑知识卡分别计数 |

## 验证与维护

```sh
python tests/test_catalog.py
python tests/test_mcts.py
python tests/test_reasoning.py
python tests/test_layered.py
python tests/test_imported.py  # 需要完整导入压缩分片
```

覆盖层绑定原条目哈希。基础库发生相关变化后，应检查差异并重建，
不能只刷新哈希让旧审核自动生效。新增源码见
`math_mcts/data/curated_seed_20261014.txt`；构建器保持新增ID稳定。

更新历史：[CHANGELOG.md](CHANGELOG.md)。项目代码采用MIT许可；
外部来源的许可和原始来源记录分别保留。独立编写的数学陈述没有复制外部教材段落。

## 严格审计修正说明（2026-10-14，修复分支）

- MCTS 加入渐进扩宽，避免宽根节点长期无法进行深层树搜索；`value_op=max` 的返回路径优先选已知最高值而非访问量。
- 概念静态检索改为对全部概念的精确评分排序，返回访问次数为0；`iterations` 保留仅为接口兼容。
- 碰撞候选根节点按领域分配预算，配对候选按排序区间确定性取样；仍是非穷尽的启发式搜索，不保证全局最优。
- 分层批次偏移均匀覆盖有界候选池，而非仅候选前27条；候选上限和批次数依然可能遗漏可用证明。
- 补充宽根、精确检索、批次尾部覆盖等回归测试，以及PR持续集成。
- **待解决**：自动发现新数学结构、语义化推理动作、形式化核验、独立反例引擎及大规模实测。现有逻辑证书只证明相对于人工审查规则的可推导性。

## 知识语义映射与全库审计（审计分支）

对于已人工审查的知识卡，可通过`math_mcts.semantic`中的`catalog_statement_sha256`
和`load_catalog_reasoning_problem`生成显式类型化规则。规则与原知识卡完整陈述快照绑定；
更改定义、条件、结论、公式或核验元数据会导致旧映射失效。规则必须显式提供`concept_id`、
`concept_sha256`；`reviewed`规则还需要`mapping_review`和`source`。

CLI 可追加`--catalog-mapped`到`derive`与`verify-derivation`，要求输入JSON规则
符合上述绑定结构。此开关仅检查一致性和审核声明，不判断审核者身份、数学真实性或新颖性。

对整合后的全部知识执行：
```sh
python -m math_mcts.audit -o catalog_audit.json --fail-on-errors
python tests/test_semantic_audit.py
```

审计严格区分错误、警告、资料性提示。检查悬空/重复先修引用、环、缺失陈述、
来源字段、内容指纹、同名条目与完全相同的陈述候选。相关文档/来源链接存在不等于
来源逐项核实，形式化证明和自动反例搜索不属于当前验收范围。

## 类型化数学语义图与独立算法基准（2026-10-14）

`python -m math_mcts compare-provers --iterations 220 -o semantic_benchmark.json`
对数学整除、包含、隶属传递给出 BFS、束搜索和 MCTS
在同一经审核 Horn 规则图中的运行结果与证书重放。
`python -m math_mcts semantic-graph reviewed_problem.json --output semantic_rules.sqlite`
从**明确审核的类型化规则**建立可查询的条件连接图。
所有新结论只表示相对这些审核规则可推导，不代表新数学成果。
知识重要性与难度审定需人工提供源指纹与理由，
使用 `tools/apply_editorial_reviews.py` 写独立审计覆盖层。
详见 [SEMANTIC_V2.md](SEMANTIC_V2.md)。

## Lean 结构提取基础与 20×20 集合论基准

`lean/ExtractCoreSmoke.lean` 已在独立 CI 中成功读取真实 Lean 的
定理类型和证明项常量引用；`lean_reference_index` 建立来源 SHA
绑定的语法依赖索引，并防止未经审核的 JSON 假冒为已经通过内核认证。
固定的 mathlib4 来源提交为 `54c01c3314d33d15d77893cbe4e0472ff26bb34d`，
需要 Lean `v4.35.0-rc4`，**原来源数学声明提取尚未完成**。

`examples/set_membership_20x20.py` 采用元素隶属关系在集合包含下传递的
有效数学规则，提供 20 层×每层 20 条的受控初等证明容量测试，
包含缺少必要包含前提的负面验证。该测试不证明研究级复杂推理或搜索优势。
详情：[LEAN_STRUCTURE_PIPELINE.md](LEAN_STRUCTURE_PIPELINE.md)。

## Lean 环境获取与来源引用（2026-10-14）

Lean Core 测试和固定版本 Mathlib 提取是两个独立的验证级别。现有固定版
Mathlib 缓存获取已调整为 **模块级下载（含其依赖）→ 限时重试 → 上游旧端点 → 单模块源码编译**，
避免一开始下载全库导致资源浪费。

```sh
python tools/build_attribution.py --db math_index.sqlite --report source_attribution_report.json
python tools/build_attribution.py --db math_index.sqlite --id KNOWLEDGE_ID
# mathlib4 源代码必须位于固定 SHA 且已有对应 Lean 环境
bash tools/bootstrap_pinned_mathlib.sh Mathlib/Algebra/Group/Basic.lean
```

索引与知识卡会显示固定来源链接；仅凭模块不能推断单条定理的发现者。
详见 [来源说明](ATTRIBUTION_AND_SOURCES.md) 和 [Lean 提取流程](LEAN_STRUCTURE_PIPELINE.md)。

## 全量 Lean 提取与署名审核（阶段 1 → 2 → 4）

参阅 [全量执行、类型语义和来源审核状态账](FULL_LEAN_EXECUTION.md)。
99,984 条 source_registry 定理全部进入一个确定性、来源 SHA 锁定的分片计划；
每个分片实际运行 Lean 后才增加提取数，未成功的来源必须保留未完成状态。
Lean 类型结构与逻辑前提判断分开存储，不自动把语法引用当作新定理。
全库来源审核队列保留原 mathlib 社区署名和许可，不把引用的数学结论当作仓库作者原创。
本轮根据要求暂停真实复杂数学证明的阶段 3。

## Level 1–3 七领域深化专题包

新增 126 条（7 域×3 层×每单元 6 条）带条件、结论、推导提示、反例和
主题来源的教学深化卡；核心记录使用 `D123_` 稳定 ID，前置关系显式核验。
卡片重要性与难度是**暂定编辑候选**，并非独立数学审核或 Lean 已证新成果。
详见 [`LEVEL123_DEEP_EXPANSION.md`](LEVEL123_DEEP_EXPANSION.md)。
