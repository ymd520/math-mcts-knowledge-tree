"""直觉先验接入测试：只测新接口，旧 collide 的置顶断言仍在 test_mcts.py。

原则：直觉分是探索先验，不是终局评分；未签名概念返回 None，
不假装有直觉；直觉版返回的对仍必须跨领域。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from math_mcts import (KnowledgeTree, collide_concepts, collide_with_intuition,
                       intuition_rules, intuition_score)


def test_intuition_score_signed_and_unsigned():
    tree = KnowledgeTree.load()
    score, rules = intuition_rules(tree, "AN21", "PR07")
    assert score == 4.0
    assert "tool_object" in rules
    assert intuition_score(tree, "AN21", "LV31405") is None
    assert intuition_rules(tree, "AN21", "LV31405") == (None, None)


def test_intuition_duality_is_real_duality_not_curated():
    tree = KnowledgeTree.load()
    # 导数 x 定积分：微积分基本定理的对偶/逆运算，不是 curated 配对。
    score, rules = intuition_rules(tree, "AN03", "AN06")
    assert score == 10.0
    assert rules["duality"] == 3.0
    assert tree.collision_note("AN03", "AN06") is None


def test_collide_with_intuition_seed():
    tree = KnowledgeTree.load()
    res = collide_with_intuition(tree, seed="傅里叶变换", top_k=5,
                                 iterations=300)
    assert len(res) == 5
    for a, b, _, _ in res:
        assert a.domain_cn != b.domain_cn
    # 预算受限的 PUCT 搜索仍应在 300 次迭代内访问到 curated 对。
    assert {"AN21", "PR07"} in [{a.id, b.id} for a, b, _, _ in res]


def test_old_collide_unchanged_by_intuition_module():
    tree = KnowledgeTree.load()
    res = collide_concepts(tree, seed="傅里叶变换", top_k=5,
                           iterations=3000)
    (a, b, _, note) = res[0]
    assert {a.id, b.id} == {"AN21", "PR07"}
    assert note and "特征函数" in note


if __name__ == "__main__":
    test_intuition_score_signed_and_unsigned()
    test_intuition_duality_is_real_duality_not_curated()
    test_collide_with_intuition_seed()
    test_old_collide_unchanged_by_intuition_module()
    print("ALL INTUITION TESTS PASSED")
