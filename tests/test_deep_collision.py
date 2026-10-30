"""深度碰撞搜索测试：小参数下验证广度、深度与确定性。

正式接口（collide_concepts）不在此改动，见 tests/test_mcts.py 的置顶回归。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_mcts import KnowledgeTree, deep_collide, DeepCollisionSearch


def _tree():
    return KnowledgeTree.load()


def test_small_pool_searches_pool_and_reaches_depth():
    tree = _tree()
    chains, fusions, stats = deep_collide(
        tree, seed="傅里叶变换", top_k=5, per_domain=5,
        beam_width=5, max_leaves=3, min_step=0.2)
    # 第一层就会把池内跨域概念评一遍：实际评过数应接近池规模。
    assert stats["pool_size"] >= 30
    assert stats["searched_concepts"] >= 20
    assert stats["pair_evals"] > 0
    assert chains, "小池下围绕傅里叶变换应至少找到一条深度链"
    assert all(len(ch.concepts) >= 2 for ch in chains)
    assert isinstance(fusions, list)


def test_deterministic_and_seed_pair():
    tree = _tree()
    kwargs = dict(top_k=3, per_domain=5, beam_width=5,
                  max_leaves=3, min_step=0.2)
    a, _, _ = deep_collide(tree, seed="傅里叶变换", **kwargs)
    b, _, _ = deep_collide(tree, seed="傅里叶变换", **kwargs)
    assert [c.ids for c in a] == [c.ids for c in b]
    chains, _, stats = deep_collide(tree, seed_pair=("AN21", "PR07"), **kwargs)
    assert chains and all("AN21" in c.ids and "PR07" in c.ids for c in chains)
    assert stats["searched_concepts"] >= 20


def test_invalid_params_rejected():
    tree = _tree()
    try:
        DeepCollisionSearch(tree, per_domain=0)
    except ValueError:
        pass
    else:
        raise AssertionError("per_domain=0 应抛 ValueError")
    try:
        DeepCollisionSearch(tree, max_leaves=1)
    except ValueError:
        pass
    else:
        raise AssertionError("max_leaves=1 应抛 ValueError")


if __name__ == "__main__":
    test_small_pool_searches_pool_and_reaches_depth()
    test_deterministic_and_seed_pair()
    test_invalid_params_rejected()
    print("ALL DEEP COLLISION TESTS PASSED")
