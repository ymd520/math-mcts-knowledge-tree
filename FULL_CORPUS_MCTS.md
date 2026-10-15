# 全量知识进入实际 MCTS 的运行流程

普通 `collide` 原来只执行 `KnowledgeTree.load()`，即精选库；大型导入知识需要额外显式加载。另一方面，索引构建器默认截断为十万条。只运行通用 `mcts(Problem)` 内核，不会自动调用任何知识。

本次把标准研究入口改为全量知识驱动：

1. 默认索引纳入全部导入分片，并核对每个分片的哈希、记录数和总量。
2. 每个新展开状态，根据研究目标和最近选用的知识重新检索。
3. 每次再从整个索引抽取探索候选，避免始终困在初始关键词短名单里。
4. MCTS 的动作是选用知识卡进入当前路径；相关性、共享词汇、领域覆盖和深度影响启发式评分。
5. 输出全库覆盖量、实际取回量、实际树中选用量、最终路径，以及知识 ID、原陈述、指纹、来源和原有核验状态。

**全库可被检索，不意味着每轮把全库全部读一遍。知识路径也不是数学证明。**

## 使用

首次不传 `--db` 时自动建立 `.cache/math_mcts/full_corpus.sqlite`，后续复用完整缓存。初始化需要解压全部分片和构建索引；本地索引属于可重建缓存，不提交 Git。

```bash
python -m math_mcts research "compact topology continuous" --iterations 1000 --depth 20 -o research.json
python -m math_mcts collide "convex optimization" --iterations 200
```

`research` 是多层研究路径；`collide` 默认调用同一全库入口的两层配对模式。要使用旧的精选库配对行为，显式指定 `--curated-only`。现有 `--levels` / `--important` 也属于显式精选库范围，因为导入记录没有得到这些等级或重要性审核。普通 `search`、教学路径和显式传入树对象的底层接口保留原本的范围。

Python 接口：

```python
from math_mcts import research_with_knowledge
report = research_with_knowledge(
    'prime polynomial divisibility', iterations=1000, depth=20, seed=7)
print(report['coverage'])
print(report['usage'])
# 由研究者或 ChatGPT 读取原陈述，再核对条件并开展数学推理。
for card in report['knowledge_records']:
    print(card['id'], card['statement'], card['attribution'])
```

如果提供现成数据库，会检查它完整覆盖当前导入清单、文档与 FTS 记录一一对应、精选输入指纹未过期。不完整或过期会报错，不退回小知识库。默认专用缓存可以自动重建。使用全部导入记录重建：

```bash
python tools/build_search_index.py --db full.sqlite
```

`--candidate-limit` 只在用户明确要求样本时使用；默认不设上限。抽样索引仍可用于已有分类、审核功能，但不能伪装成完整知识研究入口。

## 实测记录

基准为提交 `90a4260403844541e5b658ed1ca2fde626392fc0`，源数据来自真实仓库分片，未用合成记录代替规模证据。全量构建实测：

| 类别 | 实际索引记录 |
|---|---:|
| 导入知识 | 234,576 |
| 精选知识 | 11,843 |
| 合计 | 246,419 |

对不同方向各运行 120 次真实 MCTS 模拟，配置最大深度 8；下表深度为实际树深：

| 研究词 | 实际检索调用 | 树中选用导入知识 | 树中选用精选知识 | 实际树深 |
|---|---:|---:|---:|---:|
| compact topology continuous | 121 | 65 | 12 | 6 |
| convex optimization inequality | 121 | 37 | 32 | 5 |
| prime polynomial divisibility | 121 | 87 | 0 | 6 |

每项任务包含根状态及之后展开状态的检索，所以调用数为模拟数加一。树中选用记录不一定全部进入最后排名最高的路径；报告的 `on_reported_path` 单独标明它们。选用数量是不同 ID 的计数，不是证明次数。

机器可读证据包含索引元数据、各次 MCTS 统计、选用 ID/来源层/陈述指纹：[运行摘要](reports/full_corpus_mcts_20261015.json)。完整运行报告通过下面命令复现，其中含每次状态的查询、词面检索与全库探索候选 ID。

```bash
python tests/test_indexed_mcts.py
python tools/benchmark_indexed_mcts.py --db full.sqlite --iterations 120 --depth 8 --output full_corpus_mcts_benchmark.json
```

CI 在 Python 3.12 上额外构建全部导入数据并运行不同领域的真实搜索，将完整调用报告作为 `full-corpus-mcts-usage` 工件保存。原来的显式十万条来源审核流水线保留，两个范围不会混淆。

## 技术范围

- 使用 SQLite FTS5 取回有界候选；在 MCTS 中逐状态重新检索，配合全库随机 rowid 探索和 UCT 渐进展开。
- FTS 先对窄 rowid 排序，再读取命中的大陈述，避免为所有匹配行搬运 Lean JSON。
- 候选、卡片缓存有界；不是构建全库两两笛卡尔积。日志随实际展开状态数增长。
- 查询是词面匹配，不声称有语义理解、适用条件证明或自动定理发现。
- 导入难度继续为未评级，既有来源归属保留；未审核声明不自动成为可执行推理规则。
- `--depth` 是允许的知识选择深度，不保证有限预算一定到达，更不是证明深度。
- 底层通用 MCTS 仍可用于数值任务。只有调用这里的标准入口，才能声称接入了全量知识；仓库操作规则已记录这一要求。
