# 可追溯数学源码索引层

在原有知识卡、学习路径和碰撞引擎之外，增加固定版本 mathlib4 的源模块图和 UCT 搜索。源码位置索引不按 CURATION.md 中知识卡的标准混入 `math_mcts/data/knowledge.json`；它是供后续查证、选题和逐条审核使用的独立层。

固定版本：`105b9b1ce126e77b467aac6f6ba36b510ac57368`。本次本地实测：27 个编辑领域、238 个中文主题提纲、8,619 个源模块、221,184 个词法声明位置、1,212 个源目录。共 231,282 个节点。声明数量包含辅助定义、重复短名、程序基础设施，不能等同于重要数学定理数量。

## 从仓库根目录运行

Python 3.10+，SQLite 必须支持 FTS5，无第三方 Python 依赖。

```sh
python source_index/src/bootstrap.py
python source_index/src/mcts.py --query "finite group convolution" --iterations 2000 --depth 30
python source_index/src/mcts.py --query "矩阵 特征值" --iterations 1200 --depth 30
python -m unittest discover -s source_index/tests -v
```

首次 bootstrap 下载约 24 MB 的原始 mathlib4 源码，检查 SHA-256，然后构建约 305 MiB 的 SQLite 索引。需预留至少 500 MiB 磁盘空间。源码归档和数据库为可再现生成物，未提交大体积二进制到 Git；下载、许可证、固定版本与构建器均已提交。

已持有本次项目包源码归档时可离线构建：

```sh
python source_index/src/bootstrap.py --archive /path/to/mathlib4.tar.gz
```

Bootstrap 只读取与索引上游源码，不执行上游代码。归档哈希不匹配会拒绝继续。

模块、声明节点记录固定版本 GitHub 链接、路径、行号或文件哈希。读取原文：

```sh
python source_index/src/read_source.py "module:Mathlib/Analysis/Convolution.lean" --context 50
```

`reports/search.json` 保存实际搜索树的节点、父节点、访问次数、回报、随机种子与命中路径。

## 评分和边界

MCTS 实际执行选择、渐进展开、随机 rollout、回传。奖励仅为词面相关性，不是证明正确性、原创性或研究含金量。`--depth 30` 是上限，实际展开深度另行报告，不能声称完成 30 层数学推理。

知识图使用 contains、source_map、imports 三种关系。contains 是目录层级；source_map 是编辑映射；imports 是代码导入关系，不是数学定理依赖，也不等同于教学先修。搜索默认不使用 imports，可通过 `--imports` 打开；路径内禁止重复节点。

中文仅有有限常用别名，FTS 候选上限 500；不存在语义模型或 Lean 验证器。词法声明提取器不是 Lean AST，可能遗漏特殊语法声明；没有解出全限定名。本次没有安装 Lean 或重新编译上游，因此状态不标为本次形式验证通过。

238 个中文主题是提纲；统计、数值、优化、数学物理等覆盖仍需补充专门来源。此层不能宣称已收录全部数学。

来源见 [SOURCES.md](SOURCES.md)，统计见 [reports/coverage.json](reports/coverage.json)。原有知识库的实际概念数以其数据文件为准，本索引计数不与它混加。
