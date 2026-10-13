# MCTS 文本完整导入（2026-10-13）

20 份原始 TXT 全部以 `.txt.gz` 无损保存，包括知识卡、组织结构、名称索引、研究附录和许可证。用 Python `gzip.decompress` 或常见解压工具恢复原文；原文件 SHA256 见 `math_mcts/data/imported/manifest.json`。

234,576 条知识记录转换为仓库 Concept 字段结构，分为20个 `json.gz` 文件。新增字段保存完整假设、结论、原始元数据、来源、符号引用和核验状态。压缩只用于减少传输和存储，无删节。

审查范围：记录数量、字段完整性、上游定理指纹、来源提交、唯一标识、无损原文归档、加载兼容性、检索与既有回归测试。**没有逐条重新证明，没有运行 Lean 内核，也没有认证所有记录的重要性或中文释义。**标准知识卡原指纹保存在 original_metadata，转换后的 statement_sha256 对标准卡按完整陈述计算。上游定理指纹按去掉 `theorem 名称` 后的陈述计算，沿用原导出规范。

导入区是待审语料，不自动增加默认的精选知识卡；所有条目的重要性/中文释义审核状态是 pending。难度5是保守占位值，不是专家评级；空 prereq 表示未提取，不代表无需前置。声明符号引用不是证明依赖，不能用来伪造依赖图。原始“核心子库”标记只保存在元数据，未提升为“核心”标签。

## 检索和碰撞使用

```python
from math_mcts import KnowledgeTree, search_concepts, collide_concepts
# 必须限定模块；不要直接枚举全库的所有概念对。
tree = KnowledgeTree.load_imported(
    module_prefix="Mathlib.Algebra.GroupWithZero.Action.Basic",
    include_curated=False,
)
print(tree.check_integrity())
for c, visits, score in search_concepts(tree, "smul", top_k=3):
    print(c.card())
# 碰撞分数是启发式候选排序，不是新定理或证明。
```

默认 `KnowledgeTree.load()` 保持原有精选库入口。导入语料显式用 `load_imported`；它核对压缩分片 SHA256，按模块筛选，兼容既有搜索/碰撞 API。原始文本中的组织和研究附录保留在无损原文归档中，不冒充知识卡。

来源 mathlib4 固定提交 `54c01c3314d33d15d77893cbe4e0472ff26bb34d`；来源许可见仓库 `source_index/vendor/mathlib4-LICENSE`。
