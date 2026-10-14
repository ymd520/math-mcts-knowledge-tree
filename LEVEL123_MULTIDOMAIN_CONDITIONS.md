# Level 1–3 各领域重要数学知识：深度扩展 v1.13.0

## 目标与核验边界

本轮实际新增 **105 条**独立知识卡：七个标准领域 × 每领域 Level 1、2、3
各五条（每级 35 条）。精选库原条目、既有 ID、原始知识内容保持不变。

**Level 是学习难度，重要性是人工编辑评级，Lean 形式化验证又是第三个维度。**
本轮收录的是基本数学事实的独立中文整理，不是发现新定理，不宣称已由 Lean
kernel 核验，不自动将其编译为 Horn 规则。

## 领域覆盖与重点

| 主领域 | L1（入门） | L2（高中至大学入门） | L3（大学基础） |
|---|---|---|---|
| 数学基础 | 集合差、逆否、量词否定、元素证明 | 函数复合、单射、归纳、笛卡尔计数 | 逆像、等势、量词顺序、等价关系、偏序 |
| 代数 | 整除、GCD、同余、负数乘积 | 余式、同余乘法、模逆元、数列 | 子空间、谱、秩零化度、群同态、元素阶 |
| 分析 | 绝对值、不等式、单调性 | 连续、乘积求导、驻点、正项级数 | 一致连续/收敛、积分交换、绝对收敛 |
| 几何与拓扑 | 欧氏距离、三角形、相似 | 投影、旋转、二维行列式 | 开球、闭集、紧性、同胚 |
| 概率与统计 | 互斥、补事件、频率、均值 | 条件概率、独立、方差、标准误 | 条件独立、协方差、马尔可夫界、大数律 |
| 离散数学 | 计数、度数、图基本结构 | Pascal 递推、树、BFS、拓扑序 | 二分图、色数、欧拉、容斥、Hall |
| 计算与优化 | 穷举、算法不变式、二进制编码 | 二分、对数复杂度、稳定排序、凸组合 | 凸性、下降引理、投影、谱半径、强凸 |

每条的内容维度：

- `assumptions`：适用条件（条件不齐时不得使用结论）；
- `conclusion` 与 `formulas`：明确可检验的数学命题；
- `original_metadata["边界/反例"]`：典型不适用或容易混淆处；
- `original_metadata["跨领域应用"]`：潜在跨领域联系，不等于推理证明；
- `prereq`：显式编辑的课程学习依赖，**非逻辑推导边**；
- `source_url` 与 `source_locator`：现有教材/资料的**主题引用**，
  未逐条逐页核实；原始数学史发现者不在此冒认；
- `statement_sha256`：绑定“条件＋结论＋公式”，防止静默篡改；
- `verification_status`：`editorial_mathematical_statement_not_formal_proof`。

## 例：三种不同的逻辑结论

1. 只有“函数连续”不能无条件使用导数乘积法则；要求双方可导。
2. 随机变量协方差为零不代表独立，除非具有更强的分布假设。
3. 有界光滑函数沿负梯度下降的下降界需要**梯度 L-Lipschitz** 与 `L>0`，
   并不能从“函数可导”直接推出。

这些都是有边界的已知数学知识，不是生成器拼接的猜想。

## 已有知识库集成

独立数据文件：`math_mcts/data/curated/level123_multidomain_20261014.json`。

经签名 SHA-256 的 `manifest.json` 将其接入
`KnowledgeTree.load()`、`KnowledgeTree.select(levels=[1,2,3],important_only=True)`、
分层先修图、领域浏览及 MCTS 检索候选池。

新增 ID 为 `C26D0001`–`C26D0105`，保留既有条目。
只为明确的课程依赖建立 51 条连接，不以来源词相似来生成形式证明。

强约束：`tests/test_deep_level123.py` 检查记录数量、等级/领域平衡、
原始来源、条件指纹、旧库重名、依赖环、假形式化标志和文档包校验和。

## 教材来源及署名

- Oscar Levin, *Discrete Mathematics: An Open Introduction*, 4th edition：
  https://discrete.openmathbooks.org/dmoi4.html
- Jim Hefferon, *Linear Algebra*：https://hefferon.net/linearalgebra/
- Thomas W. Judson, *Abstract Algebra: Theory and Applications*：
  https://judsonbooks.org/abstract-algebra-theory-and-applications/
- Jiří Lebl, *Basic Analysis I & II*：https://www.jirka.org/ra/
- H. Pishro-Nik, *Introduction to Probability, Statistics, and Random Processes*：
  https://www.probabilitycourse.com/
- OpenStax, *Precalculus 2e*：
  https://openstax.org/books/precalculus-2e/pages/preface
- Stephen Boyd and Lieven Vandenberghe, *Convex Optimization*：
  https://web.stanford.edu/~boyd/cvxbook/
- MIT 18.335 Numerical Methods：
  https://math.mit.edu/~stevenj/18.335/

这些链接是章节主题的阅读和核查入口，**不宣称已逐页证实每条陈述对应位置**。
原教材、mathlib 形式化实现及最早数学发现均属于各自作者。
Math-MCTS 的贡献是整理、重述、建立结构与索引，不转移上游成果署名。

## 尚未解决

- 大量精选旧知识与全部 99,984 条 Lean 来源数据仍存在交叉主题，
  当前只强制审计精确标题重名，语义近重复需继续人工去重。
- Level 1、2、3 的更大规模增长须增加可核验的课程证据与独立审核，
  **不能直接给来源原先未评级的十万条定理批量贴“重要”标签**。
- 阶段 3 的研究级复杂证明与 MCTS 基准仍按此前要求暂停。
