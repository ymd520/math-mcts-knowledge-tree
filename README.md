# 数学知识 MCTS 搜索树

当前代码与整合目录版本：**v1.10.0**。纯Python标准库，Python3.9+。

将数学知识组织为领域→分支→主题→概念，支持知识检索、学习路径、知识配对，
以及相对于明确审核规则的多前提、多层推导。MCTS用于搜索调度，
搜索次数和深度不代表数学原创性或证明真实性。

## 当前知识数量

原始基础库9417条；补充390条；默认统一加载9807条。
59条旧知识补充条件、结论和参考来源；603条按依赖引用标为结构上重要，
这两类不是新增知识。原始导入语料234576条另行统计，不等于同样数量的
重要定理或已经审核的概念。

| 难度 | 重要/核心知识：之前 | 当前 |
|---|---:|---:|
| level1 初中基础 | 87 | 290 |
| level2 高中与微积分入门 | 544 | 802 |
| level3 大学基础 | 1671 | 1927 |
| level4 大学进阶 | 1442 | 1734 |

重要性、难度、内容核验程度分别记录。部分旧等级尚待重评；新卡片的编辑检查
不是Lean验证，来源网址为主题参考，不是逐条定理证明定位。
详见[目录架构](CATALOG_ARCHITECTURE.md)和[收录规范](CURATION.md)。

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
| math_mcts/search.py | 学习路径、概念检索、知识配对 |
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
