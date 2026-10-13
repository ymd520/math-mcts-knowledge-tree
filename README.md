# 数学知识 MCTS 搜索树

把**全领域数学基础与重要知识**组织成一棵**蒙特卡洛树搜索 (MCTS) 搜索树**：
知识本身就是树（领域 → 分支 → 主题 → 概念），MCTS 在这棵树上做两种智能搜索——
**学习路径规划**与**概念检索**。零第三方依赖，纯 Python 标准库。

> English: A Monte Carlo Tree Search over an integrated mathematics knowledge
> tree (7 domains, 122 concepts). MCTS plans optimal learning paths through
> prerequisite dependencies and retrieves concepts by searching the
> domain → branch → topic → concept hierarchy.

当前版本: v1.1.0（更新日志见文末）。

---

## 知识树覆盖（122 个概念，7 大领域）

| 领域 | 概念数 | 分支举例 |
|---|---|---|
| 数学基础 Foundations | 17 | 集合论、数理逻辑、证明方法 |
| 代数 Algebra | 20 | 初等代数、线性代数、抽象代数、数论 |
| 分析 Analysis | 25 | 微积分、实分析、复分析、微分方程、级数与变换 |
| 几何与拓扑 Geometry & Topology | 14 | 欧氏几何、解析几何、微分几何、拓扑学 |
| 概率与统计 Probability & Statistics | 17 | 概率论、随机变量、统计推断 |
| 离散数学 Discrete Mathematics | 13 | 组合数学、图论、离散结构 |
| 计算与优化 Computation & Optimization | 16 | 数值分析、最优化、算法数学 |

每个概念包含：中英名称、一句话定义（零基础可读）、关键公式（纯 Unicode）、
难度等级（1 入门–5 博士）、前置依赖、核心/重要标签。

## MCTS 在这里做什么

标准 MCTS 四步循环——**选择（UCB1）→ 扩展 → 模拟（随机 rollout）→ 回传**，
实现于 `math_mcts/mcts.py`，通过统一的 `Problem` 接口驱动两种搜索：

1. **学习路径规划**（`plan_learning_path`）
   在"前置依赖图"上搜索：状态 = 已学概念序列，动作 = 下一个可学的概念
   （前置已满足）。回报函数奖励"到达目标"，惩罚"难度跳跃过大"和"路径过长"。
   结果是一条**每一步的前置都已学过**的最优学习路径。

2. **概念检索**（`search_concepts`）
   在"领域 → 分支 → 主题 → 概念"层级树上搜索：动作 = 沿层级下钻，
   叶节点回报 = 查询与概念的相关度（文本重叠 + 名称命中加权 + 核心标签加成）。
   MCTS 的 UCB 机制自动把算力集中到最相关的分支——知识树**就是**搜索树。
   实现细节：知识树完全已知、叶节点评分廉价，因此模拟步采用**子树精确求值**
   （返回子树内最大相关度，而非随机 rollout）。此时 MCTS 等价于 UCB 探索引导的
   最优分支限界搜索，必收敛到全局最相关概念；`Problem.simulate` 钩子保留默认的
   随机 rollout 供其他问题使用。

## 安装

```bash
git clone https://github.com/ymd520/math-mcts-knowledge-tree.git
cd math-mcts-knowledge-tree
# 无第三方依赖，Python 3.9+ 直接运行
```

## 快速开始

```bash
# 知识库概览 + 完整性自检
python -m math_mcts info

# 规划学习路径：从零基础到"傅里叶变换"怎么学
python -m math_mcts path "傅里叶变换"

# 已掌握"条件概率"，从此之后开始规划
python -m math_mcts path "马尔可夫链" --known "条件概率"

# 检索相关概念
python -m math_mcts search "贝叶斯定理" --top_k 5

# 查看概念卡片
python -m math_mcts show "蒙特卡洛树搜索"

# 导出学习计划为 Markdown
python -m math_mcts export-path "傅里叶变换" -o 学习计划.md
```

Python API：

```python
from math_mcts import (KnowledgeTree, plan_learning_path, search_concepts,
                       export_path_markdown, to_dot)

tree = KnowledgeTree.load()          # 加载内置知识库（122 概念）

# 1. 学习路径规划（known=已掌握的概念）
path = plan_learning_path(tree, "梯度下降", iterations=3000,
                          known=["AN01", "AN03"])
for c in path:
    print(c.cn, "| 难度", c.level, "|", c.path())

# 2. 概念检索
for c, visits, score in search_concepts(tree, "机器学习 优化", top_k=5):
    print(c.cn, c.definition)

# 3. 前置依赖闭包（拓扑有序）
print(tree.prereq_closure("AN21"))   # 学傅里叶变换之前要先学什么

# 4. 导出学习计划 / 可视化某次 MCTS 搜索树
open("plan.md", "w").write(export_path_markdown(path))

from math_mcts.mcts import mcts
from math_mcts.search import ConceptSearchProblem
_, root = mcts(ConceptSearchProblem(tree, "极限"), iterations=800)
open("tree.dot", "w").write(
    to_dot(root, label_fn=lambda s: tree.hierarchy_label(s)))
# dot -Tpng tree.dot -o tree.png   （需安装 graphviz）
```

## 项目结构

```
math-mcts-knowledge-tree/
├── math_mcts/
│   ├── __init__.py        # 对外 API
│   ├── __main__.py        # CLI：path / search / info
│   ├── knowledge.py       # 概念节点、知识树加载、层级浏览、前置依赖图
│   ├── mcts.py            # MCTS 引擎（选择/扩展/模拟/回传，UCB1）
│   ├── search.py          # 两种搜索问题 + 高层 API
│   └── data/
│       └── knowledge.json # 102 个概念的全部知识数据
├── tests/test_mcts.py     # 完整性 + 路径合法性 + 检索 + MCTS 收敛性测试
├── examples/demo.py       # 演示脚本
└── README.md
```

## 扩充知识库

`math_mcts/data/knowledge.json` 是纯数据文件，欢迎按以下格式追加概念：

```json
{
  "id": "AN22",
  "domain_cn": "分析", "domain_en": "Analysis",
  "branch_cn": "微积分", "topic_cn": "一元微积分",
  "cn": "洛必达法则", "en": "L'Hôpital's Rule",
  "definition": "0/0 或 ∞/∞ 型极限等于分子分母分别求导后的极限。",
  "formulas": ["lim f/g = lim f′/g′"],
  "level": 2,
  "prereq": ["AN03"],
  "tags": ["重要"]
}
```

追加后运行自检：`python -m math_mcts info`（自动检查前置是否存在、有无循环依赖），
再跑测试：`python tests/test_mcts.py`。

## 测试

```bash
python tests/test_mcts.py
# ALL TESTS PASSED
```

## 更新日志

- **v1.1.0**（2026-10-13）：概念 102 → 122（新增对角化、伽罗瓦理论、PDE、马尔可夫链、SGD、反向传播、MCTS 自身等 20 个）；学习路径支持已知概念（`known` / `--known`）；新增 `show` 概念卡片、`export-path` 导出 Markdown 学习计划；新增 `viz.to_dot` 搜索树可视化；概念检索改用子树精确求值的模拟步（UCB 分支限界，必收敛全局最优）；`Concept.card()`。
- **v1.0.0**（2026-10-13）：首版，102 概念 / 7 领域，MCTS 学习路径规划 + 概念检索，CLI 与测试。

## License

MIT
