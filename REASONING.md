# 多知识、多层推导架构（v1.8.0）

## 实际实现范围

新增 `math_mcts/reasoning.py`。基础对象是带类型的原子命题和多前提规则，
不是概念对。多条前提共同支持一个结论形成一条有向超边；结论可作为
后续规则的前提。MCTS 在可执行超边上调度，逐步生成可重放推导证书。

这是一阶逻辑的一个受限子集：无函数符号、有限显式对象、正 Horn 规则。
变量写作 `?x`；变量必须在前提中出现；所有常量必须预先声明类型。
尚不支持存在量词见证生成、一般否定、等式重写、高阶函数、自动自然语言
或 Lean 解析。它不是全领域自动数学证明器，也不是新成果认证器。

## 调用

```sh
python -m math_mcts derive examples/extreme_value.json --iterations 80 --max-steps 50 -o report.json
python -m math_mcts verify-derivation examples/extreme_value.json report.json
python tests/test_reasoning.py
python tests/test_mcts.py
```

```python
import json
from math_mcts import load_reasoning_problem, derive, verify_certificate

with open("examples/extreme_value.json", encoding="utf-8") as f:
    book, assumptions, goal = load_reasoning_problem(json.load(f))
result = derive(book, assumptions, goal, iterations=1000, max_steps=50)
if result.certificate:
    assert verify_certificate(book, result.certificate, assumptions, goal)
```

## 数据与信任边界

输入 JSON 声明 `signatures`（谓词的参数类型）、`objects`（对象类型）、
`assumptions`、`goal`、`rules`。每条规则声明多条 `premises`、一个
`conclusion`、带类型的 `variables`、`source`、`status`。

- `reviewed`：调用方明确授权使用的规则，必须带来源；这个标签不是程序
  自动核验其数学真实性的结果。
- `candidate` / `refuted`：不参与已证推导。
- 前提固定，搜索不能添加假设，不能自动生成对象或推广猜想。
- 证书绑定规则库 SHA-256、精确目标和原始前提。验证器逐条重放变量替换、
  类型、多前提以及新增结论。规则内容、来源或对象体系变化都会使旧证书失效。
- `derived_relative_to_rules` 只说明目标可由这些前提和规则推出，
  不等于 Lean 内核验证，不证明规则本身正确，也不说明原创性。

规则使用正命题；如需区分不同函数的定义域/值域，必须把这种关系编码进
  谓词和前提，不能依赖宽泛的类型名推断。

## 搜索与图的分工

1. 从目标谓词向后收集可能相关的规则和前提谓词。这是保守相关性筛选，
   不是完整的目标反向统一求证器。
2. 在固定对象体系内向前匹配全部前提，构建可达推理超图。支持多对象变量
   替换，重复变量必须一致，不同对象不能混用。
3. MCTS 仅选择当前前提齐备、结论尚未获得的超边。达到目标奖励 1，否则 0；
   不按文字长度、知识标签或猜想数量给证明奖励。
4. 记录包括 rollout 在内的成功路径，删除与目标无关的步骤，重放证书。

同一事实集合共享动作缓存；MCTS 访问统计仍按路径保留，未冒充已实现
共享统计的图搜索算法。`effective_depth` 是目标证明依赖链的最长长度；
`applied_rules` 是目标依赖子图中的规则应用次数；它们不同于迭代次数。

`max_steps` 限制整条调度路径的规则应用次数，`max_edges` / `max_rounds`
限制预构图。预算截断有明确记录；`not_found_within_budget` 不是反证。
`scope_complete` 只表示当前目标相关 Horn 规则的前向构图已达到不动点，
不表示全部数学知识被搜索完，也不表示 MCTS 穷尽所有路径。

小型有限 Horn 问题直接前向闭包通常已经足够。这里的 MCTS 是兼容后续
研究动作的调度接口，不声称它比闭包更快。目前预构图仍可能昂贵；不适合
把 23 万条原始文本直接全量转成规则后无限配对。

## Discovery–Verification 分离

`DiscoveryQueue.propose()` 保存猜想及反例检验方向；
`DiscoveryQueue.ingest_concepts(tree)` 接入现有 `KnowledgeTree`，保留知识 ID。
文本和 Lean 原文只进入未验证候选区，不自动变成推理规则。

```python
from math_mcts import KnowledgeTree, DiscoveryQueue
tree = KnowledgeTree.load_imported(
    module_prefix=["Mathlib.Algebra.Ring", "Mathlib.Analysis.SpecialFunctions.Log"],
    include_curated=False)
queue = DiscoveryQueue()
queue.ingest_concepts(tree)
```

下一步需对候选知识完成精确命题翻译、条件检查、规则审核，才能加入 RuleBook。
队列目前不自动创造新结构或搜索反例；外部发现器/反例程序可生产候选，
形式验证适配器可核验规则，但这些后端尚未接入。不存在自动从“猜想”晋升为
“已证”的路径。原有 `collide_concepts` 保留为候选知识配对检索接口。

## Rules

`examples/extreme_value.json` 是人工整理的已知极值定理演示：

- `compact(X)`：X 是紧拓扑空间；`nonempty(X)`：X 非空。
- `continuous(f,X)`：f 在 X 上连续。
- `image(f,X,I)`：I 正是 f 在 X 上的像；`real_set(I)`：I 是实数的子集。
- `compact_image`：连续映射把紧空间映为紧集。
- `nonempty_image`：函数在非空定义域上的像非空。
- `compact_real_extrema`：非空实数紧集有最大值和最小值。
- `attainment`：像集的最大值和最小值由定义域中的点取得。

结论：f 在 X 上取得最大值和最小值。4 次规则应用，最长依赖深度为 3。
这些是已知数学事实，用于验证工程连接机制，不是原创研究成果。对象 I 显式
给出，程序不生成函数像。X 的拓扑和 f 的值域含义由上述谓词语义约定。

## 验证范围

测试覆盖多前提合流、逐条删除必要条件、对象错配、类型/元数错误、重复变量、
未审核及已反驳规则隔离、循环自举、证书篡改、版本变化、预算截断和事实状态缓存。
另有人工构造的 20 层规则链，验证报告统计实际深度，并不宣称 20 层原创数学推理。
完整示例的所有 32 种前提子集都接受检查。CLI 输出可独立重放。
