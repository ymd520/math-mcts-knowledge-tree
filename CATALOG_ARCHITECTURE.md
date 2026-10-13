# v1.10.0 知识架构与level1–4扩充

## 本次实际增量

基础库9417条保持原文件和原ID。新增390条，整合后9807条。
449条独立编写的教材基础陈述中，59条同名或经显式检查的同义陈述
在原ID上补充条件、结论和公式；没有把它们重新计为新增知识。
另外603条旧知识被至少2条现有知识引用为前置，按“被使用”规则标为结构上重要。
这603条不计为新增知识，不改变原内容核验状态。

| 等级 | 重要/核心：之前 | 之后 | 增加 |
|---|---:|---:|---:|
| 1 | 87 | 290 | 203 |
| 2 | 544 | 802 | 258 |
| 3 | 1671 | 1927 | 256 |
| 4 | 1442 | 1734 | 292 |
| 合计 | 3744 | 4753 | 1009 |

Level1的重要知识为原来的约3.33倍。其它等级也扩充，但未宣称每个等级翻倍。
完整前后清单见 `math_mcts/data/curated/inventory_20261014.json`。

## 等级、重要性、真伪是不同维度

- level1：初中基础；level2：高中与微积分入门；level3：大学基础；
  level4：大学进阶；level5：研究生或前沿。
- `重要`依据课程基础性或显式前置引用，不以level高低决定重要性。
- `verification_status`记录内容核验程度。新增条目是人工表述和编辑检查，
  不等于逐条文献定位、不等于独立审计、不等于Lean内核验证。
- `source_locator`明确标记主题参考。网址不能冒充该条定理的精确证明定位。
- 本次纠正可测空间、测度空间、几乎处处、拓扑和等明显难度错标。
  历史库其它评级仍可能不一致，尚未逐条完成全面重评。

## 整合架构

`KnowledgeTree.load()`统一读取：

1. 原始基础JSON。
2. SHA-256校验过的level压缩JSON分片补充包。
3. 绑定原条目内容哈希的编辑覆盖层。

旧内容变化时，相关覆盖层拒绝加载，避免把旧审核默默套用到新内容。
自定义JSON路径不自动混入补充包。`include_supplements=False`可读取原始基础库。
分片源码是 `math_mcts/data/curated_seed_20261014.txt`；
`tools/build_curated_catalog.py`可复现构建，新增ID使用规范化标题哈希，
向源码追加新条目不会导致已有新增条目的ID整体重排。
分片采用确定性gzip压缩，原始可读知识源码单独保留，减少重复字段的传输与存储成本。

默认精选库、导入语料、知识检索、配对碰撞、Discovery候选队列共用Concept结构。
导入语料可通过 `load_imported(..., include_curated=True)`带入补充包；
所有知识文本仍需精确翻译和审核才能成为 `RuleBook` 中的规则。
没有把390条新增文本自动声称为已经可执行的证明规则。

## 检索与碰撞

```sh
python -m math_mcts info
python -m math_mcts search "分数除法" --levels 1,2 --important
python -m math_mcts search "支配收敛" --levels 3,4 --important --domain 分析
python -m math_mcts collide --levels 1,2,3,4 --important --top_k 10
```

```python
from math_mcts import KnowledgeTree, search_concepts, collide_concepts, DiscoveryQueue

full = KnowledgeTree.load()
scope = full.select(levels=[1,2,3,4], important_only=True)
print(scope.inventory())
matches = search_concepts(scope, "零概率 不可能", top_k=10)
pairs = collide_concepts(scope, top_k=10)
queue = DiscoveryQueue()
queue.ingest_concepts(scope)  # 进入未验证候选，不自动晋升为规则
```

`select()`是检索/碰撞视图，保留真实前置ID，记录视图外前置；规划学习路径
应使用完整树。`find_all()`返回同名或别名全部精确匹配，避免默默合并不同数学对象。
已有72组同名条目没有被盲目删除；新包没有新增同名组。
显式同义映射登记在构建器CANONICAL表中。其它语义去重仍需审核，
规范化标题去重不能识别全部同义定理。

层级构建改为集合去重，避免反复线性扫描已有孩子；碰撞重要性排序检查全部标签，
不再只看标签列表第一项。搜索文本包括适用条件、结论、模块与别名。
MCTS仍是有界候选搜索，不保证有限预算下的全局最优或原创突破。

## 内容和来源范围

扩充覆盖算术、分数、比例、方程、几何测量、逻辑与证明、三角恒等式、
向量、微积分、计数、概率、线性代数、分析、抽象代数、测度、统计推断、
凸优化与数值方法。条件与结论分栏，新增definition≤80字、example≤60字。

参考资源登记于生成脚本的SOURCES表：OpenStax教材主题页、Lebl分析教材、
Levin离散数学、Hefferon线性代数、Pishro-Nik概率教材、Judson抽象代数、
Tao测度论、MIT数值方法、Boyd/Vandenberghe凸优化。所有陈述独立编写；
未复制教材段落、图片或整章内容。来源登记为主题参考，不计作逐条来源核验。

前置依赖目前编码了部分课程先修关系，`prereq_status`明确说明不是完整证明
假设图。定理的真正适用条件保存在 `assumptions` 中。

## 维护和验证

```sh
python tools/build_curated_catalog.py
python tests/test_catalog.py
python tests/test_mcts.py
python tests/test_reasoning.py
python tests/test_layered.py
```

构建器仅用于已审核的源码变化。基础库更新使覆盖层失效时，应检查变动后重建，
不应只刷新哈希来掩盖内容差异。
测试覆盖数量、等级/重要性独立、类型、长度、条件与来源字段、稳定ID、
去重、别名、导入适配、哈希篡改、过期覆盖层、检索与旧接口兼容性。
