# 每层 20 个知识点、至少 20 层（v1.9.0）

新增 `math_mcts/layered.py`，在 v1.8.0 类型化多前提推理层之上实现同步批次碰撞。
原有 `derive`、知识检索和配对接口仍可使用。

## 精确含义

“一个知识点”是一个已知且精确区分对象的原子命题，而不是关键词或搜索访问。
每层使用至少 20 个不同前提命题，按多前提规则生成新结论。单次规则应用
可以使用 20 个或更多前提；每层也可以包含多次规则应用。

默认最低宽度为 20，最低层数为 20，最大层数为 20。可以配置为 30、50 等
更深/更宽的预算。候选规则不足时报告不足，不复制已有条目凑数。
不同层可以复用仍然成立的知识；每一条推理必须消费至少一个上一层新结论。

每层只读取上一层结束时的事实快照；同层产生的结论不能在同层再次使用。
同一结论每层只能生成一次。证书验证同时要求：

1. 固定前提、规则库版本、对象类型及全部规则条件一致。
2. 每层实际使用至少 20 个不同前提。
3. 每层在最终目标的证明依赖子图中，也至少有 20 个不同前提；无关分支不能凑数。
4. 层数至少 20；目标的实际最长证明依赖深度至少 20。提前达到浅层目标后
   无法用空循环或无关推导补成成功。

这不保证每次输入都能完成 20 层。严格条件可能导致搜索失败；失败只意味着
当前输入及搜索预算未获得证书，不是数学反证。多个目标中至少一个需要达到
指定深度，不要求每个目标都一样深。宽度统计是前提节点数，不是定理规则数。

## 调用

```python
from math_mcts import LayerConfig, derive_layers, replay_layers

config = LayerConfig(min_knowledge=20, min_layers=20, max_layers=30,
                     batch_width=20, max_candidates=2000, batch_choices=8)
result = derive_layers(book, assumptions, goals, config=config,
                       iterations=100, seed=7)
if result["certificate"]:
    assert replay_layers(book, result["certificate"], assumptions, goals, config)
```

`book` 仍然是明确审核的 `RuleBook`；`assumptions` 是固定原始前提；`goals`
是一个或多个精确命题。可通过 `load_layered_problem()` 读取 JSON。
格式复用原有对象/规则格式，新增 `goals` 数组和 `layer_config` 配置。

```sh
# 创建可复现的合成依赖图输入：每层20个输出，每个输出依赖上层全部20个知识点
python examples/layered_collision.py --width 20 --layers 20 -o layered_problem.json
python -m math_mcts derive-layers layered_problem.json --iterations 5 --seed 7 -o layered_report.json
python -m math_mcts verify-layers layered_problem.json layered_report.json

# 验证更宽、更深的配置
python examples/layered_collision.py --width 21 --layers 21 -o layered_problem.json
```

## 架构与成本

- 先从目标向后筛选相关规则，再逐层向前匹配当前可执行规则。
- 每次碰撞把一组规则组成批次。MCTS 的一次动作是推进一整层，
  不再把一次规则应用直接当作整层。
- `batch_width` 是每个批次最多产生多少个不同新结论，不是最低知识输入数；
  一条含 20 个前提的规则也可形成一层。
- 每个状态只构建一次谓词索引，供全部规则共享；相同事实集合和上一层
  前沿共享候选批次缓存。相同批次的不同排列被合并。
- 每个状态最多保留 `max_candidates` 个候选推理边；最多提出
  `batch_choices` 个批次。避免枚举全部子集或全部 20 层组合。
- 当前批次策略是有界轮转启发式，可能漏掉有价值的组合。截断记录在
  `candidate_truncated`；`search_complete` 始终为 false。不声称穷尽搜索。
- CLI 把完整证书保存到输出文件，终端只展示指标，避免大批推理记录刷屏。

报告逐层区分实际参与知识、上一层新知识、新结论、规则应用数、目标相关
知识数及实际依赖深度；同时记录到达层数、预算和不足位置。

## 已运行的验证

20×20 合成测试中，每层 20 个新结论，每条规则使用上层全部 20 个前提：
总共 400 次规则应用，8000 次前提引用，目标实际深度 20。全部 400 次应用
都属于最终目标的依赖子图。三个随机种子的结果见
[layered_validation.json](examples/layered_validation.json)。

另测 21×21、每层20前提/1结论、删除必要前提、重复前提、证书篡改、
同层依赖、无关分支凑宽度、浅层目标和候选预算截断。

这些是人工指定逻辑蕴含关系的工程测试，不是 400 个新数学定理，也不是
数学研究突破。已有知识文本仍需精确翻译与规则审核后才能作为已证规则使用。
未新增自动 Lean 翻译、Lean 内核、通用新结构发现或自动反例后端。
