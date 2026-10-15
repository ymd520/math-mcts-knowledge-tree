# 通用数学 MCTS v3：增量推理图与自适应求解

## 独立定位

Math-MCTS 是不依赖任何特定猜想的通用数学研究基础设施。所有优化
必须适用于多学科、一般数学结构；一个特定开放问题只能作为外部测试集，
不能决定软件核心架构。

## 本轮完成的架构变更

旧 `ProofGraph.build` 在每一轮对**全部旧事实**重新连接每一条规则的前提，
当证明链很深时会重复生成大量同样的规则实例。

新增 `math_mcts.incremental_graph.build_incremental_graph`：

1. 将事实分成历史全集 `facts` 与**上轮新增** `delta`。
2. 根据谓词建立事实索引。
3. 每次规则实例化必须有至少一个前提匹配 `delta`，其余前提匹配旧事实全集。
4. 先绑定增量事实，然后按照谓词候选桶的大小匹配剩余前提。
5. 对重复变量、常量、排序与多前提连接保留原 `RuleBook` 的类型约束。
6. 对生成的超边做精确去重，按轮更新事实（同轮新结论不可立即作为前提）。
7. 保留边数、轮数预算，以及 `fixed_point` / `round_budget` /
   `edge_budget` 的完整性标记。

**重要边界：** 这是已审核、正向、无函数项 Horn 规则的增量实例化。
它不是复杂数学公式的自动 Lean 翻译、内核级证明，也不是原创定理生成器。
当规则变量存在大量组合时，连接仍可能呈组合爆炸；不能承诺渐近线性速度。

## 可验证的迁移策略

```python
graph_old = ProofGraph.build(book, assumptions, goal, strategy="reference")
graph_new = ProofGraph.build(book, assumptions, goal, strategy="incremental")
assert graph_old.complete == graph_new.complete
assert set(graph_old.edges) == set(graph_new.edges)
```

在两个图都是完整且预算充足时要求边集合严格相同。预算截断时，
由于边枚举顺序不同，允许返回不同的**部分**候选边，但必须标记
不完整，不能声称找不到定理的证明。

- `ProofGraph.build` 默认继续提供 `reference` 实现，保留可审计对照。
- `derive` 默认用增量实现，也可用 `graph_strategy="reference"` 回退。
- `solve_adaptive` 使用增量推理图；小图仍由 BFS 处理；
  较大图先尝试可重放的确定性 Horn 闭包，
  仅在没有预算内见证时采用原有启发式搜索。
- 新候选数学资料只能以 `status=candidate` 进入类型检查，不可偷偷成为
  `RuleBook` 的 `reviewed` 公理或推出未验证结论。

## 单次命令、基准与审查

```bash
python tests/test_incremental_graph.py
python tests/test_reasoning.py
python tests/test_lean_adaptive.py
python tools/benchmark_incremental_graph.py --repetitions 3 --depth 80 --breadth 45 --output incremental_graph_benchmark.json
```

对照覆盖现有数学任务、随机规则图、量词绑定的有限元实例、
重复变量、循环依赖、零前提规则、非审核候选、长链及超预算情况。
速度基准只对同一程序环境中、相同规则图的构建耗时进行观察，
不强制设置“新算法必须更快”的假设性断言。

## 下一轮通用优化方向（尚未实现）

- 按数学表达式类型进行有约束的知识召回，避免仅按名称联想；
- 针对等式重写、全称/存在量词、高阶表达式，设计独立审计的类型化规则层；
- 建立跨领域、完全隔离训练/开发与测试来源的数学问题集，检查候选召回、
  实际证明率、误报率、内存峰值、跨随机种子稳定性和搜索开销；
- 验证多表示转换、新不变量设计、反例寻找是否真的提高原创发现能力。

本轮不增加未经审核的“重要数学定理”数量，不提前声称突破重大开放问题。
目录版本号仅在原有唯一 manifest 位置维护，本轮未改变版本号。
