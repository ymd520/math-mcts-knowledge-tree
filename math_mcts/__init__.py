"""math-mcts: 把全领域数学知识组织成 MCTS 搜索树.

知识树: 领域 -> 分支 -> 主题 -> 概念, 数据见 data/knowledge.json.
学习路径使用严格先修拓扑闭包，静态检索使用精确排序；
MCTS 用于有界知识配对和人工审核规则下的推导调度。
"""
from .knowledge import Concept, KnowledgeTree
from .mcts import mcts, Problem
from .search import (plan_learning_path, search_concepts,
                     export_path_markdown, collide_concepts,
                     collision_score)
from .viz import to_dot
from .reasoning import (Atom, Rule, RuleBook, Certificate, ProofGraph,
                        DiscoveryQueue, derive, verify_certificate,
                        load_reasoning_problem, load_certificate)
from .layered import (LayerConfig, LayerCertificate, derive_layers, replay_layers,
                      load_layered_problem, load_layer_certificate)
from .semantic import catalog_statement_sha256, load_catalog_reasoning_problem
from .fast_index import build_index, fast_search, index_stats
from .semantic_links import compatible_atoms, find_composable_rules
from .scale_plan import expansion_status
from .knowledge_bank import KnowledgeBank, classify_knowledge

__version__ = "1.12.0"
__all__ = ["Concept", "KnowledgeTree", "Problem", "mcts",
           "plan_learning_path", "search_concepts",
           "export_path_markdown", "to_dot",
           "collide_concepts", "collision_score",
           "Atom", "Rule", "RuleBook", "Certificate", "ProofGraph",
           "DiscoveryQueue", "derive", "verify_certificate", "load_reasoning_problem",
           "load_certificate", "LayerConfig", "LayerCertificate", "derive_layers",
           "replay_layers", "load_layered_problem", "load_layer_certificate",
           "catalog_statement_sha256", "load_catalog_reasoning_problem",
           "build_index", "fast_search", "index_stats",
           "compatible_atoms", "find_composable_rules", "expansion_status",
           "KnowledgeBank", "classify_knowledge"]


