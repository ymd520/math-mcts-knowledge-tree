"""演示: MCTS 在数学知识树上的两种搜索."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from math_mcts import KnowledgeTree, plan_learning_path, search_concepts

tree = KnowledgeTree.load()
print(f"知识库: {len(tree.concepts)} 个概念, "
      f"{len(tree.domains())} 个领域\n")

print("=" * 60)
print("演示 1: 学习路径规划 —— 目标: 傅里叶变换")
print("=" * 60)
path = plan_learning_path(tree, "傅里叶变换", iterations=3000)
for i, c in enumerate(path, 1):
    print(f"  {i:2d}. [{c.id}] {c.cn} (难度{c.level}) — {c.path()}")
print(f"\n共 {len(path)} 步, 每一步的前置都已在前面学过.\n")

print("=" * 60)
print("演示 2: 概念检索 —— 查询: '机器学习 优化 梯度'")
print("=" * 60)
for c, visits, mean in search_concepts(tree, "机器学习 优化 梯度",
                                       top_k=5, iterations=2000):
    print(f"  [{c.id}] {c.cn} | {c.path()} | 相关度 {mean:.2f}")
    print(f"       {c.definition[:60]}…")
