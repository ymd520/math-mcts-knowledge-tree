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
from .intuition import (IntuitionCollisionProblem, collide_with_intuition,
                        intuition_score, intuition_rules)
from .deep_collision import (DeepChain, DeepCollisionSearch, DeepFusion,
                             deep_collide)
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
from .equational import (Term, Equation, RewriteRule, EquationBook,
                         RewriteCertificate, prove_equation, verify_rewrite_certificate)
from .logic_router import (solve_problem, verify_problem,
                           load_equational_problem, load_rewrite_certificate)
from .finite_logic import (Formula, FiniteCertificate, prove_finite,
                           verify_finite_certificate)
from .conditional_logic import (ConditionalRule, ConditionalBook,
                                GuardedCertificate, prove_guarded,
                                verify_guarded_certificate)

from .ai_knowledge import (
    validate_pack, ingest_pack as ingest_ai_pack, ingest_file as ingest_ai_file,
    inventory as ai_knowledge_inventory, lookup as search_ai_candidates,
    candidate_tree as ai_candidate_tree, query_for_research,
    collide_for_research,
)

from .field_audit import audit_fields, load_taxonomy, choose_audit_queue

from .version import CATALOG_VERSION
from .indexed_mcts import research_with_knowledge, validate_full_index, ensure_full_index

__version__ = CATALOG_VERSION
__all__ = ["Concept", "KnowledgeTree", "Problem", "mcts",
           "plan_learning_path", "search_concepts",
           "export_path_markdown", "to_dot",
           "collide_concepts", "collision_score",
           "IntuitionCollisionProblem", "collide_with_intuition",
           "intuition_score", "intuition_rules",
           "DeepChain", "DeepCollisionSearch", "DeepFusion", "deep_collide",
           "Atom", "Rule", "RuleBook", "Certificate", "ProofGraph",
           "DiscoveryQueue", "derive", "verify_certificate", "load_reasoning_problem",
           "load_certificate", "LayerConfig", "LayerCertificate", "derive_layers",
           "replay_layers", "load_layered_problem", "load_layer_certificate",
           "catalog_statement_sha256", "load_catalog_reasoning_problem",
           "build_index", "fast_search", "index_stats",
           "compatible_atoms", "find_composable_rules", "expansion_status",
           "KnowledgeBank", "classify_knowledge",
           "Term", "Equation", "RewriteRule", "EquationBook",
           "RewriteCertificate", "prove_equation", "verify_rewrite_certificate",
           "solve_problem", "verify_problem", "load_equational_problem",
           "load_rewrite_certificate",
           "Formula", "FiniteCertificate", "prove_finite", "verify_finite_certificate",
           "ConditionalRule", "ConditionalBook", "GuardedCertificate",
           "prove_guarded", "verify_guarded_certificate",
           "validate_pack", "ingest_ai_pack", "ingest_ai_file",
           "ai_knowledge_inventory", "search_ai_candidates",
           "ai_candidate_tree", "query_for_research", "collide_for_research",
           "audit_fields", "load_taxonomy", "choose_audit_queue",
           "research_with_knowledge", "validate_full_index", "ensure_full_index"]


