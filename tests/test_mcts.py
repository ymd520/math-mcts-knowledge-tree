"""math-mcts 项目测试: 知识图谱完整性 + MCTS 两类搜索."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from math_mcts import (KnowledgeTree, plan_learning_path, search_concepts,
                        export_path_markdown, to_dot)
from math_mcts.mcts import Problem, mcts
from math_mcts.search import ConceptSearchProblem


def test_integrity():
    tree = KnowledgeTree.load()
    assert len(tree.concepts) >= 90, "概念数量不足"
    assert tree.check_integrity() == [], "完整性自检未通过"


def test_prereq_closure_order():
    tree = KnowledgeTree.load()
    closure = tree.prereq_closure("AN21")  # 傅里叶变换
    assert "AN20" in closure and "AN13" in closure  # 傅里叶级数、复数
    # 拓扑有序: 每个概念的前置都排在它前面
    pos = {cid: i for i, cid in enumerate(closure)}
    for cid in closure:
        for p in tree.get(cid).prereq:
            assert pos[p] < pos[cid], f"{cid} 的前置 {p} 排在后面"


def test_plan_learning_path():
    tree = KnowledgeTree.load()
    path = plan_learning_path(tree, "傅里叶变换", iterations=3000)
    ids = [c.id for c in path]
    assert ids[-1] == "AN21", "路径终点必须是目标概念"
    # 路径中每个概念的前置必须更早出现(学习顺序合法)
    seen = set()
    for cid in ids:
        for p in tree.get(cid).prereq:
            assert p in seen, f"{cid} 的前置 {p} 未在路径中先学"
        seen.add(cid)
    print("path:", " -> ".join(c.cn for c in path))


def test_plan_reaches_with_prereq_chain():
    tree = KnowledgeTree.load()
    path = plan_learning_path(tree, "贝叶斯定理", iterations=1500)
    ids = [c.id for c in path]
    assert ids[-1] == "PR03"
    assert "PR02" in ids and "PR01" in ids  # 条件概率、概率公理在路径中


def test_search_concepts():
    tree = KnowledgeTree.load()
    res = search_concepts(tree, "极限", top_k=3, iterations=1500)
    top_names = [c.cn for c, _, _ in res]
    assert "极限" in top_names, f"检索'极限'未命中: {top_names}"
    res2 = search_concepts(tree, "贝叶斯定理", top_k=3, iterations=1500)
    assert "贝叶斯定理" in [c.cn for c, _, _ in res2]
    res3 = search_concepts(tree, "最短路", top_k=3, iterations=1500)
    assert "最短路" in [c.cn for c, _, _ in res3]


def test_mcts_on_toy_problem():
    # 玩具问题: 在二叉树上找最大叶子值, MCTS 应收敛到最优路径
    values = {"L": 1.0, "R": 0.0}

    class Toy(Problem):
        def initial_state(self): return "root"
        def actions(self, s):
            return {"root": ["L", "R"], "L": [], "R": []}[s]
        def step(self, s, a): return a
        def terminal(self, s): return s in values
        def reward(self, s): return values[s]

    seq, _ = mcts(Toy(), iterations=500, seed=1)
    assert seq == ["L"], f"MCTS 未收敛到最优: {seq}"


def test_plan_with_known():
    tree = KnowledgeTree.load()
    known = ["AN01", "AN03"]  # 已掌握极限、导数
    path = plan_learning_path(tree, "泰勒级数", iterations=2000,
                              known=known)
    ids = [c.id for c in path]
    assert ids[:2] == known, f"路径应从已知概念开始: {ids[:3]}"
    assert ids[-1] == "AN19"


def test_concept_card():
    tree = KnowledgeTree.load()
    card = tree.find("梯度下降").card()
    assert "梯度下降" in card and "定义" in card and "前置" in card


def test_export_markdown():
    tree = KnowledgeTree.load()
    path = plan_learning_path(tree, "贝叶斯定理", iterations=1500)
    md = export_path_markdown(path)
    assert "# 学习计划" in md and "贝叶斯定理" in md


def test_viz_dot():
    tree = KnowledgeTree.load()
    problem = ConceptSearchProblem(tree, "极限")
    _, root = mcts(problem, iterations=300, seed=7, max_depth=6)
    dot = to_dot(root, label_fn=lambda s: tree.hierarchy_label(s))
    assert dot.startswith("digraph") and "访问" in dot


def test_concept_count_grown():
    tree = KnowledgeTree.load()
    assert len(tree.concepts) >= 120, "v1.1 概念数应 ≥120"
    assert tree.check_integrity() == []


if __name__ == "__main__":
    test_integrity()
    test_prereq_closure_order()
    test_plan_learning_path()
    test_plan_reaches_with_prereq_chain()
    test_search_concepts()
    test_mcts_on_toy_problem()
    test_plan_with_known()
    test_concept_card()
    test_export_markdown()
    test_viz_dot()
    test_concept_count_grown()
    print("ALL TESTS PASSED")
