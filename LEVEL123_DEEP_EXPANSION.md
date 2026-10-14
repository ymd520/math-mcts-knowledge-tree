# Level 1–3 跨领域重要数学知识：专题深化包

## 第一轮新增范围与定位

第一轮新增 **126 条**独立撰写的教学/研究工具卡；2026-10-14第二轮再增加15条，累计141条。
覆盖 7 个原有精选库领域 × Level 1、2、3 × 每单元 6 条：

| 领域 | Level 1 | Level 2 | Level 3 |
| --- | ---: | ---: | ---: |
| 数学基础 | 6 | 6 | 6 |
| 代数（含初等数论、线性代数及群论） | 6 | 6 | 6 |
| 分析（极限、微积分与收敛） | 6 | 6 | 6 |
| 几何与拓扑（欧氏几何、度量与连通紧性） | 6 | 6 | 6 |
| 概率与统计（事件、期望、集中及条件化） | 6 | 6 | 6 |
| 离散数学（计数、图论、匹配及网络） | 6 | 6 | 6 |
| 计算与优化（数值误差、收敛及凸优化） | 6 | 6 | 6 |

Level 1 注重问题类型、适用条件、逆命题错误；
Level 2 注重结构性推导、解题步骤及正确性不变量；
Level 3 注重重要连接定理、收敛/最优性证书与跨学科桥梁。

## 每条资料是什么

源文件：[`math_mcts/data/level123_deep.tsv`](math_mcts/data/level123_deep.tsv)。

新记录保留：知识名称与英文对照、明确假设、精确结论、关键公式、
简要证明思路、一个明确误用或反例、可理解的应用情景、
教学所需的前置知识和标明范围的参考来源。原有精选卡与
99,984 条 mathlib 来源定理**不改名、不自动调级、不改变结论**。

程序生成确定性 ID，按完整中文标题检测与所有现有精选卡的重复；
前置概念均须真实存在，不许自动由模糊文本相似度生成“因果证明链”。
搜索结果、知识卡和 MCTS 概念加载会包含这些记录，并在卡上显示
“证明/求解思路”和“误用与反例”。

## 来源和真正的审核状态

资料表中的参考书目是**主题参考**，并非对每一条陈述在原文中
具体页码、定理编号及历史最初发现人的逐项考证。
独立撰写教学提要不代表发现数学结论。
引用参考以原作品作者、出版社或教学项目为准：
- Jiří Lebl，《Basic Analysis I & II》
- Jim Hefferon，《Linear Algebra》
- Thomas Judson，《Abstract Algebra: Theory and Applications》
- MIT OpenCourseWare 6.042J，《Mathematics for Computer Science》
- MIT OpenCourseWare 18.901，《Introduction to Topology》
- Hossein Pishro-Nik，《Introduction to Probability, Statistics, and Random Processes》
- Stephen Boyd / Lieven Vandenberghe，《Convex Optimization》
- MIT 18.335 数值方法；Oscar Levin 离散数学；OpenStax 大学代数

每条记录显示：
- `curation_status = editorial_candidate_not_independently_reviewed`
- `verification_status = authored_standard_fact_not_kernel_verified`
- `reference_relation = topic_reference_not_statement_certification`
- `knowledge_origin = authored_study_summary_of_existing_mathematics_not_new_discovery`

`重要` 表示**为深化检索筛选而提出的重要性编辑候选**，不是已有数学家
逐条复核的质量认证；Level 1–3 亦为面向学习的暂定难度，不是定理的新颖性等级。
本批新增的 Lean 内核证明数为 0；也未自行升级任何 mathlib 原来源的评级。
未来须逐条补充精确来源位置、可靠的定理条件证明和外部独立复核，
才能变更其审查标记。

## 怎样调用与审计

```sh
python tests/test_catalog.py
python tests/test_deep_core.py
python tools/audit_level123_depth.py --output level123_deep_audit.json

# 通过既有 KnowledgeTree API 使用
python - <<'PY'
from math_mcts.knowledge import KnowledgeTree
tree=KnowledgeTree.load()
subset=tree.select(levels=[1,2,3],important_only=True)
print(len(subset.concepts))
print(tree.find('全称存在量词换序风险').card())
PY
```

审核应着重检查每条假设是否必要、结论是否有反例、公式所用
空间及域是否正确、重要性是否确实高于知识库同义项，并区分
“教学先修”与“证明的逻辑前提”。

## 本批工程验收

- 第一轮覆盖 7 域 × 3 层，每个单元 6 条；补充轮加入15条经缺口筛选的专题卡。
- 累计141条均有前提、结论、公式、证明思路、误用反例与例子；
- 不引入完全同名知识，前置知识不能悬空或越级；
- 审计报告记录跨领域的显式先修关系；
- 永不把引用 mathlib 的成果冒认为用户原创；
- Python 3.10/3.12 回归与完整精选库审计必须通过。

两轮扩充合计141条，是高质量新增知识的初步供给，不声称填满十万条重要知识、
自动证明 G5C 或已达到研究级 20 层 × 20 条搜索效果。


## 第二轮：缺口筛选专题卡（2026-10-14）

新增15条，覆盖七个领域的高价值补充主题：对象类型检查、可数乘积基数、Burnside定理、Maschke定理、阿尔泽拉–阿斯科利、Fubini、Stone–Weierstrass、球面盈余、不变域、条件期望的L²收缩、McDiarmid、Cramér–Wold、König无限引理、浮点中点溢出规避及Runge现象。

这是在既有11,364条精选知识和第一轮126条专题卡基础上继续扩充。新卡仍标为人工撰写、未独立数学复核、未通过Lean内核；主题参考不等于逐条文献定位。新增前按规范化标题对基础库、已审核补充分片及第一轮专题卡作精确重名检查，未发现标题重复。语义同义项仍须人工持续审核。
