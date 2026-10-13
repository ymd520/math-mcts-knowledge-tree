"""math-mcts: 把全领域数学知识组织成 MCTS 搜索树.

知识树: 领域 -> 分支 -> 主题 -> 概念, 数据见 data/knowledge.json.
MCTS 引擎对这棵树做两种搜索:
  - plan_learning_path: 规划"从基础到目标"的最优学习路径
  - search_concepts:     关键词检索最相关的概念
"""
from .knowledge import Concept, KnowledgeTree
from .mcts import mcts, Problem
from .search import (plan_learning_path, search_concepts,
                     export_path_markdown, collide_concepts,
                     collision_score)
from .viz import to_dot

__version__ = "1.3.0"
__all__ = ["Concept", "KnowledgeTree", "Problem", "mcts",
           "plan_learning_path", "search_concepts",
           "export_path_markdown", "to_dot",
           "collide_concepts", "collision_score"]
